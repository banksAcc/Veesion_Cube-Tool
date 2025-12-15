"""
Webcam test runner.
Configurazione tramite Variabili Globali.
"""
import sys
from pathlib import Path
import yaml
import cv2
import numpy as np

from algo import (
    estimate_truncated_ico_from_image, 
    load_camera_calibration, 
    load_ico_transforms
)
from config_models import AppConfig 

# ==========================================
# CONFIGURAZIONE GLOBALE (PARAMETRI UTENTE)
# ==========================================
CONFIG_FILE = Path("config.yaml")

# Geometria Reale Oggetto
ICO_RADIUS_METERS = 0.05678     # Raggio dal centro del solido alla faccia (11 cm)

# Tuning Algoritmo
MIN_MARKER_AREA_PX = 300.0   # Scarta marker più piccoli di questi pixel
WEIGHT_EXPONENT = 2        # 2.0 = Quadratico (privilegia marker grandi)
OUTLIER_THRESHOLD = 0.09     # 8 cm: distanza massima dalla media per essere valido

# Camera
CAMERA_ID_OVERRIDE = None    # Se None, usa quello nel config.yaml
# ==========================================


def _load_config(path: Path) -> AppConfig:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return AppConfig.from_mapping(data)

def main() -> int:
    # 1. Caricamento Risorse
    print(f"Caricamento configurazione da {CONFIG_FILE}...")
    cfg = _load_config(CONFIG_FILE)
    
    calib_path = cfg.pose.camera_calibration_npz
    trans_path = cfg.pose.ico.transform_file
    
    # Caricamento K, dist
    K, dist = load_camera_calibration(str(calib_path))
    
    # Caricamento e SCALING delle trasformazioni
    # Le trasformazioni nel JSON sono unitarie (raggio=1). 
    # Le moltiplichiamo qui per il raggio reale.
    transforms_raw = load_ico_transforms(str(trans_path))
    transforms_scaled = {}
    
    print(f"Applicazione scala raggio: {ICO_RADIUS_METERS}m")
    for key, T in transforms_raw.items():
        T_real = T.copy()
        # Scaliamo solo il vettore traslazione (ultime 3 righe, colonna 3)
        # Assumendo T sia 4x4
        T_real[:3, 3] *= ICO_RADIUS_METERS
        transforms_scaled[key] = T_real

    # Parametri marker dal config
    marker_size_m = float(cfg.pose.ico.marker_size_mm) / 1000.0
    dictionary = cfg.pose.ico.dictionary

    # 2. Setup Camera
    cam_id = CAMERA_ID_OVERRIDE if CAMERA_ID_OVERRIDE is not None else cfg.capture.camera_id
    cap = cv2.VideoCapture(int(cam_id))
    
    if not cap.isOpened():
        print("Errore apertura camera.")
        return 1

    print("Tracking avviato. Premi 'q' per uscire.")
    
    while True:
        ret, frame = cap.read()
        if not ret: break

        # 3. Loop Principale
        try:
            result = estimate_truncated_ico_from_image(
                image=frame,
                K=K,
                dist=dist,
                transforms=transforms_scaled, # Passiamo quelle già scalate
                aruco_dict=dictionary,
                marker_size=marker_size_m,
                
                # Parametri passati dalle GLOBALI
                min_marker_area_px=MIN_MARKER_AREA_PX,
                weight_exponent=WEIGHT_EXPONENT,
                outlier_distance_threshold=OUTLIER_THRESHOLD,
                
                return_overlay=True
            )
            
            final_img = result.get("overlay", frame)
            
        except ValueError:
            # Errori attesi (nessun marker, etc)
            final_img = frame
        except Exception as e:
            print(f"Errore runtime: {e}")
            final_img = frame

        cv2.imshow("Ico Tracker Test", final_img)
        if cv2.waitKey(200) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    return 0

if __name__ == "__main__":
    sys.exit(main())