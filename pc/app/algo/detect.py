# pc/app/algo/detect.py
import cv2 as cv
import numpy as np
from dataclasses import dataclass
from typing import List, Optional

# Mappa dei dizionari supportati
DICT_MAP = {
    "4X4_50": cv.aruco.DICT_4X4_50,
    "5X5_50": cv.aruco.DICT_5X5_50,
    "6X6_50": cv.aruco.DICT_6X6_50,
    # Aggiungi altri se necessario
}

@dataclass
class MarkerDetection:
    id: int
    corners: np.ndarray  # Shape (4, 2)
    area_px: float

def detect_markers(img_bgr: np.ndarray, dict_name: str) -> List[MarkerDetection]:
    """Rileva marker ArUco nell'immagine."""
    if dict_name not in DICT_MAP:
        raise ValueError(f"Dizionario ArUco sconosciuto: {dict_name}")

    aruco_dict = cv.aruco.getPredefinedDictionary(DICT_MAP[dict_name])
    params = cv.aruco.DetectorParameters()
    detector = cv.aruco.ArucoDetector(aruco_dict, params)

    gray = cv.cvtColor(img_bgr, cv.COLOR_BGR2GRAY)
    corners, ids, _ = detector.detectMarkers(gray)

    detections = []
    if ids is not None:
        ids_flat = ids.flatten()
        criteria = (cv.TERM_CRITERIA_EPS + cv.TERM_CRITERIA_MAX_ITER, 30, 0.001)
        for i, marker_id in enumerate(ids_flat):
            cv.cornerSubPix(gray, corners[i], (5, 5), (-1, -1), criteria)
            c = corners[i].reshape(4, 2).astype(np.float32)
            # Calcolo area approssimativa (prodotto vettoriale)
            area = 0.5 * np.abs(np.dot(c[:, 0], np.roll(c[:, 1], 1)) - np.dot(c[:, 1], np.roll(c[:, 0], 1)))
            detections.append(MarkerDetection(int(marker_id), c, float(area)))
    
    return detections