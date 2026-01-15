import numpy as np
import cv2
import cv2.aruco as aruco
import glob
import os

cv2.setNumThreads(0)          # usa tutti i core disponibili
cv2.setUseOptimized(True)     # abilita ottimizzazioni interne

def calibrate_charuco():
    # --- 1. CONFIGURAZIONE PARAMETRI ---
    IMAGES_DIR = 'calibrazione_balser_15-01-2026'
    EXTENSION = '*.tiff' # O *.png

    # Parametri della ChArUco Board
    SQUARES_X = 12
    SQUARES_Y = 9
    SQUARE_LENGTH = 0.030
    MARKER_LENGTH = 0.022
    
    ARUCO_DICT = aruco.getPredefinedDictionary(aruco.DICT_5X5_50)

    # Creazione della board
    board = aruco.CharucoBoard(
        (SQUARES_X, SQUARES_Y), 
        SQUARE_LENGTH, 
        MARKER_LENGTH, 
        ARUCO_DICT
    )
    
    # --- CORREZIONE PRINCIPALE PER OPENCV >= 4.7.0 ---
    # --- Detector ArUco (più trasparente per debug rispetto a CharucoDetector.detectBoard) ---
    detector_params = aruco.DetectorParameters()
    try:
        aruco_detector = aruco.ArucoDetector(ARUCO_DICT, detector_params)  # OpenCV >= 4.7
    except AttributeError:
        aruco_detector = None  # fallback: useremo aruco.detectMarkers
    # ------------------------------------------------------------------------
# --- 2. CARICAMENTO IMMAGINI E RILEVAMENTO ---
    print(f"Ricerca immagini in: {os.path.join(IMAGES_DIR, EXTENSION)}")
    images = glob.glob(os.path.join(IMAGES_DIR, EXTENSION))
    
    if len(images) < 10:
        print(f"Trovate {len(images)} immagini. ATTENZIONE: Poche immagini.")
        if len(images) == 0:
            return

    print(f"Trovate {len(images)} immagini. Inizio elaborazione...")

    all_charuco_corners = []
    all_charuco_ids = []
    image_size = None

    valid_images = 0

    for image_file in images:
        # Leggi TIFF/PNG/JPG in modo robusto (supporta 8/16 bit e grayscale)
        img = cv2.imread(image_file, cv2.IMREAD_UNCHANGED)
        if img is None:
            print(f"⚠️ Immagine non valida: {image_file}")
            continue

        # Gestione canali: (H,W) / (H,W,1) / BGR / BGRA
        if img.ndim == 2:
            gray = img
        elif img.ndim == 3 and img.shape[2] == 1:
            gray = img[:, :, 0]
        elif img.ndim == 3 and img.shape[2] == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        elif img.ndim == 3 and img.shape[2] == 4:
            gray = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
        else:
            print(f"⚠️ Formato immagine non supportato: shape={img.shape} file={image_file}")
            continue

        # Normalizza a uint8 se necessario (molti TIFF sono uint16)
        if gray.dtype != np.uint8:
            gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

        if image_size is None:
            image_size = (gray.shape[1], gray.shape[0])  # (width, height)

        # 1) Detect marker ArUco
        if aruco_detector is not None:
            marker_corners, marker_ids, rejected = aruco_detector.detectMarkers(gray)
        else:
            marker_corners, marker_ids, rejected = aruco.detectMarkers(gray, ARUCO_DICT, parameters=detector_params)

        print("marker_ids:", None if marker_ids is None else len(marker_ids))

        if marker_ids is None or len(marker_ids) == 0:
            print(f"❌ Nessun marker ArUco trovato in: {image_file}")
            continue

        # 2) Interpola corner ChArUco
        retval, charuco_corners, charuco_ids = aruco.interpolateCornersCharuco(
            marker_corners, marker_ids, gray, board
        )

        # Alcune versioni possono restituire retval=None; gestiamolo
        retval_val = 0 if retval is None else int(retval)
        print("interpolate retval:", retval_val)
        print("charuco:", None if charuco_corners is None else len(charuco_corners))

        # Soglia "chiave" (presa dal tuo esempio): almeno 20 corner ChArUco
        if charuco_corners is not None and retval_val > 20:
            all_charuco_corners.append(charuco_corners)
            all_charuco_ids.append(charuco_ids)
            valid_images += 1
            print(f"✅ Rilevata board valida in: {image_file}")
        else:
            print(f"❌ Board non sufficientemente visibile in: {image_file}")

    print(f"--- RILEVAMENTO COMPLETATO ---")
    print(f"Immagini valide per la calibrazione: {valid_images}/{len(images)}")

    if valid_images < 10:
        print("ATTENZIONE: Meno di 10 immagini valide. La calibrazione potrebbe essere imprecisa.")
        if valid_images == 0:
            return

    # --- 3. CALIBRAZIONE DELLA CAMERA ---
    print("Esecuzione calibrazione...")
    
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