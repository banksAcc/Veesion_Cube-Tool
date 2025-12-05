# pc/app/algo/pnp.py
import cv2 as cv
import numpy as np
from dataclasses import dataclass
from typing import List, Tuple
from .detect import MarkerDetection # Nota il punto .

@dataclass
class MarkerPose:
    id: int
    rvec: np.ndarray # (3, 1)
    tvec: np.ndarray # (3, 1)
    R: np.ndarray    # (3, 3) Matrice di rotazione

def _get_marker_object_points(side_length: float) -> np.ndarray:
    """Restituisce i 4 angoli del marker nello spazio 3D locale (Z=0)."""
    h = side_length / 2.0
    return np.array([
        [-h,  h, 0], [ h,  h, 0], [ h, -h, 0], [-h, -h, 0]
    ], dtype=np.float32)

def estimate_marker_poses(
    detections: List[MarkerDetection], 
    K: np.ndarray, 
    dist: np.ndarray, 
    marker_size: float
) -> List[MarkerPose]:
    
    obj_points = _get_marker_object_points(marker_size)
    poses = []

    for det in detections:
        # Usa IPPE_SQUARE per maggiore precisione sui marker piatti
        ok, rvecs, tvecs, _ = cv.solvePnPGeneric(
            obj_points, 
            det.corners.reshape(4, 1, 2), 
            K, 
            dist, 
            flags=cv.SOLVEPNP_IPPE_SQUARE
        )
        
        if ok and len(rvecs) > 0:
            # solvePnPGeneric può ritornare più soluzioni, prendiamo la prima
            rvec, tvec = rvecs[0], tvecs[0]
            R, _ = cv.Rodrigues(rvec)
            poses.append(MarkerPose(det.id, rvec, tvec, R))
            
    return poses