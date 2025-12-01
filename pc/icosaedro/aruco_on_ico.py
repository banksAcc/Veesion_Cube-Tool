import cv2
import numpy as np
import json
import os
from scipy.spatial.transform import Rotation as R
from typing import Tuple, Dict, List, Optional

# ============================
# CONFIGURAZIONE E COSTANTI
# ============================

# File paths
CALIB_PATH = "../calib/calib_data.npz"         # File calibrazione camera
TRANSFORMS_PATH = "transforms_face_to_body.json" # File generato nello step precedente

# Dimensioni fisiche
MARKER_LENGTH_MM = 21.0   # Lato del marker stampato
AXIS_LENGTH_MM = 15.0     # Lunghezza assi visualizzati

# MAPPING ARUCO -> ID FACCIA (DA VERIFICARE CON IL TUO SOLIDO REALE)
# Associo gli ID ArUco che hai fornito agli ID logici delle facce (P0..P11, H0..H19)
# Logica usata qui: prendo i tuoi ID in ordine e li assegno a P0, P1... e H0, H1...

TRANSFORMS_PATH = "transforms_face_to_body.json"

MARKER_LENGTH_MM = 21.0
AXIS_LENGTH_MM = 10.0
SPHERE_RADIUS_MM = 58.0  # Raggio approssimativo dell'icosaedro per il disegno

ARUCO_TO_FACE_MAP = {
    # Sintassi:  ID_ARUCO : "ID_GEOMETRICO"
    1: "H5",
    2: "H2",
    3: "P0",   # FACCIA DI SOPRA
    4: "H3",
    5: "H0",
    6: "H6",  
    7: "P2",  
    8: "P8",
    9: "H8",
    10: "H4",
    11: "P1",
    12: "H9",
    13: "P7",
    14: "P6",
    15: "H15",
    16: "P4",
    17: "H1",    
    18: "H7",
    19: "H14",
    20: "H17",
    21: "H19",
    22: "P3",
    23: "H13",
    24: "P11",
    25: "P5",
    26: "P10",
    27: "H10",   
    28: "H16", # FACCIA DI SOTTO, SENZA PENTANGONO (DOVE STALA PENNA)
    29: "H11",    
    30: "H18",
    31: "H12",
}


# ============================
# UTILS: GESTIONE POSE E SFERA
# ============================

def average_poses(poses_list: List[np.ndarray]) -> np.ndarray:
    """
    Calcola la media geometrica di una lista di matrici 4x4.
    Posizione: Media aritmetica.
    Rotazione: Media dei Quaternioni.
    """
    if not poses_list:
        return np.eye(4)
    
    # 1. Media delle posizioni (X, Y, Z)
    translations = np.array([T[:3, 3] for T in poses_list])
    avg_translation = np.mean(translations, axis=0)
    
    # 2. Media delle rotazioni (usando Scipy Rotation)
    rot_matrices = [T[:3, :3] for T in poses_list]
    rotations = R.from_matrix(rot_matrices)
    avg_rotation = rotations.mean() # Scipy gestisce la media dei quaternioni
    
    # 3. Ricostruzione matrice media
    T_avg = np.eye(4)
    T_avg[:3, :3] = avg_rotation.as_matrix()
    T_avg[:3, 3] = avg_translation
    
    return T_avg

class SphereRenderer:
    """Genera e disegna una sfera wireframe."""
    def __init__(self, radius, rings=10, sectors=15):
        self.radius = radius
        self.points_3d = self._generate_sphere_points(radius, rings, sectors)
        self.rings = rings
        self.sectors = sectors

    def _generate_sphere_points(self, radius, rings, sectors):
        points = []
        # Generazione coordinate sferiche
        for i in range(rings + 1):
            theta = i * np.pi / rings # Latitudine (0 a pi)
            for j in range(sectors):
                phi = j * 2 * np.pi / sectors # Longitudine (0 a 2pi)
                x = radius * np.sin(theta) * np.cos(phi)
                y = radius * np.sin(theta) * np.sin(phi)
                z = radius * np.cos(theta)
                points.append([x, y, z])
        return np.array(points, dtype=np.float32)

    def draw(self, img, K, dist, T_cam_body):
        """Proietta e disegna la sfera sull'immagine."""
        # Proietta i punti 3D usando la posa del corpo
        rvec, _ = cv2.Rodrigues(T_cam_body[:3, :3])
        tvec = T_cam_body[:3, 3]
        
        img_pts, _ = cv2.projectPoints(self.points_3d, rvec, tvec, K, dist)
        img_pts = img_pts.reshape(-1, 2).astype(int)
        
        # Disegna le linee (connessioni griglia)
        # Nota: logica semplificata per disegnare "rings" e "sectors"
        pts_grid = img_pts.reshape(self.rings + 1, self.sectors, 2)
        
        color = (255, 100, 0) # Blu scuro/Arancio
        
        # Disegna paralleli (rings)
        for i in range(self.rings + 1):
            cv2.polylines(img, [pts_grid[i]], isClosed=True, color=color, thickness=1)
            
        # Disegna meridiani (sectors)
        for j in range(self.sectors):
            meridian = pts_grid[:, j, :]
            cv2.polylines(img, [meridian], isClosed=False, color=color, thickness=1)

# ============================
# LOGICA DI VISIONE
# ============================

def load_data():
    D = np.load(CALIB_PATH)
    K = D.get("K") or D.get("cameraMatrix")
    dist = D.get("dist") or D.get("distCoeffs")
    
    with open(TRANSFORMS_PATH, 'r') as f:
        transforms_data = json.load(f)
    transforms = {k: np.array(v) for k, v in transforms_data.items()}
    
    return K, dist, transforms

def main():
    try:
        K, dist, transforms = load_data()
        print("Dati caricati.")
    except Exception as e:
        print(f"Errore caricamento: {e}")
        return

    # Detector setup
    try:
        d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        p = cv2.aruco.DetectorParameters()
        detector = cv2.aruco.ArucoDetector(d, p)
    except:
        # Fallback vecchie versioni
        d = cv2.aruco.Dictionary_get(cv2.aruco.DICT_4X4_50)
        p = cv2.aruco.DetectorParameters_create()
        detector = None 

    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    
    # Inizializziamo il renderer della sfera
    sphere = SphereRenderer(radius=SPHERE_RADIUS_MM)

    print("Premi 'q' per uscire.")

    while True:
        ret, frame = cap.read()
        if not ret: break
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # 1. Detection Marker
        if detector:
            corners, ids, rejected = detector.detectMarkers(gray)
        else:
            corners, ids, rejected = cv2.aruco.detectMarkers(gray, d, parameters=p)
            
        valid_body_poses = []
        
        if ids is not None and len(ids) > 0:
            ids = ids.flatten()
            
            # Stima posa per ogni marker
            # Nota: usiamo estimatePoseSingleMarkers per semplicità qui, oppure solvePnP manuale
            # Per consistenza con lo script precedente, usiamo solvePnP nel loop se la funzione aruco non c'è
            # Qui uso una logica ibrida veloce
            
            # Definiamo i punti 3D del marker
            mh = MARKER_LENGTH_MM / 2.0
            obj_pts = np.array([[-mh,mh,0],[mh,mh,0],[mh,-mh,0],[-mh,-mh,0]], dtype=np.float32)
            
            for i, marker_id in enumerate(ids):
                # SolvePnP per il singolo marker
                success, rvec, tvec = cv2.solvePnP(obj_pts, corners[i], K, dist, flags=cv2.SOLVEPNP_IPPE_SQUARE)
                
                if success:
                    # Matrice Marker -> Camera
                    R_mat, _ = cv2.Rodrigues(rvec)
                    T_cam_marker = np.eye(4)
                    T_cam_marker[:3, :3] = R_mat
                    T_cam_marker[:3, 3] = tvec.reshape(3)
                    
                    # Recupero Matrice Faccia -> Body
                    face_id = ARUCO_TO_FACE_MAP.get(marker_id)
                    if face_id and face_id in transforms:
                        T_face_body = transforms[face_id]
                        
                        # Calcolo Posa Body proposta da QUESTO marker
                        # T_cam_body = T_cam_marker * T_face_body
                        T_cam_body_candidate = T_cam_marker @ T_face_body
                        valid_body_poses.append(T_cam_body_candidate)
                        
                        # (Opzionale) Disegno assi sui marker per debug
                        cv2.drawFrameAxes(frame, K, dist, rvec, tvec, 10.0)

        # 2. Media delle Pose e Disegno Sfera
        if valid_body_poses:
            # Calcoliamo la "Super Posa" media
            T_avg = average_poses(valid_body_poses)
            
            # Estraiamo vettori per disegnare
            rvec_avg, _ = cv2.Rodrigues(T_avg[:3, :3])
            tvec_avg = T_avg[:3, 3]
            
            # A. Disegno ASSI DEL SISTEMA CORPO (Al centro della sfera)
            # Li facciamo belli grandi
            cv2.drawFrameAxes(frame, K, dist, rvec_avg, tvec_avg, AXIS_LENGTH_MM * 2)
            
            # B. Disegno SFERA WIREFRAME
            sphere.draw(frame, K, dist, T_avg)
            
            # C. Info Testuali
            xyz = tvec_avg
            txt = f"BODY POSE (Markers: {len(valid_body_poses)})"
            txt_coords = f"X:{xyz[0]:.1f} Y:{xyz[1]:.1f} Z:{xyz[2]:.1f}"
            
            # Un riquadro semi-trasparente per il testo
            cv2.rectangle(frame, (10, 10), (350, 70), (0,0,0), -1)
            cv2.putText(frame, txt, (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1)
            cv2.putText(frame, txt_coords, (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

        cv2.imshow("Tracking Body & Sphere", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()