import numpy as np
import cv2
import cv2.aruco as aruco
import glob
import os

def calibrate_charuco():
    # --- 1. CONFIGURAZIONE PARAMETRI ---
    # Percorso delle immagini
    IMAGES_DIR = 'img'
    EXTENSION = '*.jpg' # Modifica in *.png se le tue immagini sono png

    # Parametri della ChArUco Board (come da tua specifica)
    SQUARES_X = 9           # Numero di quadrati sull'asse X
    SQUARES_Y = 12          # Numero di quadrati sull'asse Y
    SQUARE_LENGTH = 0.030   # 30 mm in metri
    MARKER_LENGTH = 0.022   # 22 mm in metri
    
    # Dizionario ArUco specificato
    ARUCO_DICT = aruco.getPredefinedDictionary(aruco.DICT_5X5_50)

    # Creazione della board
    # Nota: La sintassi può variare leggermente a seconda della versione di OpenCV.
    # Questa è per le versioni recenti (4.x).
    board = aruco.CharucoBoard(
        (SQUARES_X, SQUARES_Y), 
        SQUARE_LENGTH, 
        MARKER_LENGTH, 
        ARUCO_DICT
    )
    
    # Per visualizzare i detection, crea il detector parameters
    params = aruco.DetectorParameters()

    # --- 2. CARICAMENTO IMMAGINI E RILEVAMENTO ---
    print(f"Ricerca immagini in: {os.path.join(IMAGES_DIR, EXTENSION)}")
    images = glob.glob(os.path.join(IMAGES_DIR, EXTENSION))
    
    if len(images) < 10:
        print("ERRORE: Trovate troppe poche immagini. Assicurati che il percorso sia corretto.")
        return

    print(f"Trovate {len(images)} immagini. Inizio elaborazione...")

    all_charuco_corners = []  # Angoli rilevati in tutte le immagini
    all_charuco_ids = []      # ID rilevati in tutte le immagini
    image_size = None         # Dimensione dell'immagine (deve essere uguale per tutte)

    valid_images = 0

    for image_file in images:
        img = cv2.imread(image_file)
        if img is None:
            continue

        # Converti in scala di grigi
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Imposta image_size alla prima iterazione
        if image_size is None:
            image_size = gray.shape[::-1]

        # Rileva i marker ArUco grezzi
        corners, ids, rejected = aruco.detectMarkers(gray, ARUCO_DICT, parameters=params)

        # Se sono stati trovati marker sufficienti, raffina per trovare gli angoli ChArUco
        if len(corners) > 0:
            # Interpola gli angoli della scacchiera basandosi sui marker trovati
            response, charuco_corners, charuco_ids = aruco.interpolateCornersCharuco(
                markerCorners=corners,
                markerIds=ids,
                image=gray,
                board=board
            )

            # Se la risposta è positiva e ci sono abbastanza angoli (es. > 4)
            if response > 0 and charuco_corners is not None and len(charuco_corners) > 4:
                all_charuco_corners.append(charuco_corners)
                all_charuco_ids.append(charuco_ids)
                valid_images += 1
                # print(f"Ok: {image_file} - Angoli trovati: {len(charuco_corners)}")
            else:
                print(f"Scartata (pochi angoli ChArUco): {image_file}")
        else:
            print(f"Scartata (nessun marker): {image_file}")

    print(f"\n--- RILEVAMENTO COMPLETATO ---")
    print(f"Immagini valide per la calibrazione: {valid_images}/{len(images)}")

    if valid_images < 10:
        print("Troppe poche immagini valide per una buona calibrazione.")
        return

    # --- 3. CALIBRAZIONE DELLA CAMERA ---
    print("Esecuzione calibrazione (potrebbe richiedere tempo)...")
    
    try:
        ret, camera_matrix, dist_coeffs, rvecs, tvecs = aruco.calibrateCameraCharuco(
            charucoCorners=all_charuco_corners,
            charucoIds=all_charuco_ids,
            board=board,
            imageSize=image_size,
            cameraMatrix=None,
            distCoeffs=None
        )

        print(f"Reprojection Error: {ret}")
        print("Camera Matrix:\n", camera_matrix)
        print("Distortion Coefficients:\n", dist_coeffs)

        # --- 4. SALVATAGGIO ---
        output_filename = "calibration_data.npz"
        np.savez(
            output_filename, 
            cameraMatrix=camera_matrix, 
            distCoeffs=dist_coeffs,
            reprojError=ret
        )
        print(f"\nFile salvato con successo: {output_filename}")

    except Exception as e:
        print(f"Errore durante la calibrazione: {e}")

if __name__ == "__main__":
    calibrate_charuco()