import cv2
import numpy as np
import glob
import os

# --- 1. INIZIALIZZAZIONE ---

# Carica i dati di calibrazione della fotocamera
try:
    with np.load('calib_data.npz') as data:
        camera_matrix = data['cameraMatrix']
        dist_coeffs = data['distCoeffs']
except FileNotFoundError:
    print("Errore: file 'calib_data.npz' non trovato. Assicurati che sia nella stessa cartella dello script.")
    exit()

# Definisci le dimensioni del marker in metri (5.5 cm)
marker_size_m = 0.055

# Seleziona il dizionario ArUco corretto
aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)

# Inizializza i parametri per il rilevatore ArUco
aruco_params = cv2.aruco.DetectorParameters()

# --- 2. PERCORSO E CARICAMENTO DELLE IMMAGINI ---

# Specifica il percorso della cartella contenente le immagini
# SOSTITUISCI 'percorso/alla/tua/cartella' CON IL TUO PATH REALE
image_folder_path = 'img/' 

# Trova tutte le immagini con estensione .jpg nella cartella
image_paths = glob.glob(os.path.join(image_folder_path, '*.png'))

if not image_paths:
    print("Nessuna immagine .jpg trovata nella cartella specificata.")
    exit()

print(f"Trovate {len(image_paths)} immagini nella cartella specificata.")

# --- 3. CICLO DI ANALISI DELLE IMMAGINI ---

# Definiamo i punti 3D degli assi X, Y, Z per il disegno
# Questi punti sono posizionati al centro del marker
axis_points = np.float32([[0, 0, 0], [marker_size_m, 0, 0], [0, marker_size_m, 0], [0, 0, -marker_size_m]]).reshape(-1, 3)

for image_path in image_paths:
    frame = cv2.imread(image_path)
    if frame is None:
        print(f"Errore: impossibile caricare l'immagine {image_path}")
        continue

    print(f"\n--- Analisi di: {os.path.basename(image_path)} ---")
    gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    detector = cv2.aruco.ArucoDetector(aruco_dict, aruco_params)
    corners, ids, rejected = detector.detectMarkers(gray_frame)
    poses = []

    if ids is not None and len(ids) > 0:
        cv2.aruco.drawDetectedMarkers(frame, corners, ids)

        rvecs, tvecs, _ = cv2.aruco.estimatePoseSingleMarkers(
            corners,
            marker_size_m,
            camera_matrix,
            dist_coeffs
        )
        
        for i in range(len(ids)):
            rvec, tvec = rvecs[i], tvecs[i]
            
            # --- MODIFICA PER SOSTITUIRE drawAxis ---
            # Proietta i punti 3D degli assi sull'immagine 2D
            imgpts, _ = cv2.projectPoints(axis_points, rvec, tvec, camera_matrix, dist_coeffs)

            # Disegna gli assi sull'immagine
            origin = tuple(imgpts[0].ravel().astype(int))
            x_end = tuple(imgpts[1].ravel().astype(int))
            y_end = tuple(imgpts[2].ravel().astype(int))
            z_end = tuple(imgpts[3].ravel().astype(int))

            # Disegna le linee colorate per gli assi (B, G, R)
            cv2.line(frame, origin, x_end, (0, 0, 255), 3)  # Asse X (Rosso)
            cv2.line(frame, origin, y_end, (0, 255, 0), 3)  # Asse Y (Verde)
            cv2.line(frame, origin, z_end, (255, 0, 0), 3)  # Asse Z (Blu)
            
            poses.append({'rvec': rvec[0], 'tvec': tvec[0]})

    if len(poses) > 0:
        all_tvecs = np.array([p['tvec'] for p in poses])
        all_rvecs = np.array([p['rvec'] for p in poses])

        mean_tvec = np.mean(all_tvecs, axis=0)
        mean_rvec = np.mean(all_rvecs, axis=0)
        
        print(f"ID Marker Trovati: {ids.flatten()}")
        print(f"Posa media del cubo -> T: {np.round(mean_tvec, 3)}, R: {np.round(mean_rvec, 3)}")
        
        # --- CODICE AGGIUNTIVO PER DISEGNARE IL CUBO IDEALE ---
        # Se abbiamo una posa media, disegniamo il cubo ideale
    if len(poses) > 0:
        # Definisci le coordinate 3D degli 8 vertici del cubo
        # Il cubo ha un lato di 0.06 m.
        side = 0.06 
        half_side = side / 2.0
        
        # I vertici sono definiti rispetto al centro del marker (0,0,0)
        # L'asse Z è rivolto verso la fotocamera, quindi usiamo un valore negativo
        cube_points = np.float32([
            [-half_side, -half_side, -half_side],
            [ half_side, -half_side, -half_side],
            [ half_side,  half_side, -half_side],
            [-half_side,  half_side, -half_side],
            [-half_side, -half_side,  half_side],
            [ half_side, -half_side,  half_side],
            [ half_side,  half_side,  half_side],
            [-half_side,  half_side,  half_side]
        ]).reshape(-1, 3)

        # Proietta i punti 3D del cubo sull'immagine 2D usando la posa media
        img_cube_points, _ = cv2.projectPoints(
            cube_points,
            mean_rvec,
            mean_tvec,
            camera_matrix,
            dist_coeffs
        )

        # Converti i punti proiettati in interi
        img_cube_points = np.int32(img_cube_points).reshape(-1, 2)

        # Disegna le 12 linee che formano il cubo
        # Colore della linea (255, 255, 0) è Cyan
        color = (255, 255, 0)
        thickness = 2
        
        # Lati della base posteriore
        cv2.line(frame, img_cube_points[0], img_cube_points[1], color, thickness)
        cv2.line(frame, img_cube_points[1], img_cube_points[2], color, thickness)
        cv2.line(frame, img_cube_points[2], img_cube_points[3], color, thickness)
        cv2.line(frame, img_cube_points[3], img_cube_points[0], color, thickness)
        
        # Lati della base anteriore
        cv2.line(frame, img_cube_points[4], img_cube_points[5], color, thickness)
        cv2.line(frame, img_cube_points[5], img_cube_points[6], color, thickness)
        cv2.line(frame, img_cube_points[6], img_cube_points[7], color, thickness)
        cv2.line(frame, img_cube_points[7], img_cube_points[4], color, thickness)
        
        # Connessioni tra le due basi
        cv2.line(frame, img_cube_points[0], img_cube_points[4], color, thickness)
        cv2.line(frame, img_cube_points[1], img_cube_points[5], color, thickness)
        cv2.line(frame, img_cube_points[2], img_cube_points[6], color, thickness)
        cv2.line(frame, img_cube_points[3], img_cube_points[7], color, thickness)


    else:
        print("Nessun marker trovato in questa immagine.")

    cv2.imshow('ArUco Detection Result', frame)
    key = cv2.waitKey(0) & 0xFF
    if key == ord('q'):
        break




cv2.destroyAllWindows()
print("\nAnalisi completata.")