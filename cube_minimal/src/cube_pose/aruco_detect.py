from dataclasses import dataclass
from typing import List, Tuple
import numpy as np
import cv2 as cv

# Mappa dei dizionari supportati
DICT_MAP = {
    "4X4_50": cv.aruco.DICT_4X4_50,
    "4X4_100": cv.aruco.DICT_4X4_100,
    "5X5_50": cv.aruco.DICT_5X5_50,
    "6X6_50": cv.aruco.DICT_6X6_50,
    "7X7_50": cv.aruco.DICT_7X7_50,
    "APRILTAG_36h11": cv.aruco.DICT_APRILTAG_36h11,
}

@dataclass
class MarkerDetection:
    """Rilevazione base di un marker."""
    id: int
    corners: np.ndarray  # (4,2) float32, ordine: tl, tr, br, bl

def make_detector(dict_name: str) -> cv.aruco.ArucoDetector:
    """Crea un ArUco detector dal nome dizionario."""
    dict_id = DICT_MAP.get(dict_name)
    if dict_id is None:
        valid = ", ".join(sorted(DICT_MAP))
        raise ValueError(
            f"Unknown dictionary '{dict_name}'. Valid options: {valid}"
        )
    d = cv.aruco.getPredefinedDictionary(dict_id)
    p = cv.aruco.DetectorParameters()
    return cv.aruco.ArucoDetector(d, p)

def detect_markers(img_bgr: np.ndarray, dict_name: str) -> List[MarkerDetection]:
    """
    Esegue la detection ArUco sull'immagine BGR.
    Returns:
        Lista di MarkerDetection in ordine di rilevazione.
    """
    det = make_detector(dict_name)
    gray = cv.cvtColor(img_bgr, cv.COLOR_BGR2GRAY)
    corners, ids, _ = det.detectMarkers(gray)
    out: List[MarkerDetection] = []
    if ids is None:
        return out
    for i, mid in enumerate(ids.flatten()):
        out.append(MarkerDetection(int(mid), corners[i].reshape(4,2).astype(np.float32)))
    return out
