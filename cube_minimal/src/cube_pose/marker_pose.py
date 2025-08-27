from dataclasses import dataclass
from typing import List, Tuple
import numpy as np
import cv2 as cv

@dataclass
class MarkerPose:
    """Posa stimata per singolo marker nel frame camera."""
    id: int
    rvec: np.ndarray   # (3,1) Rodrigues
    tvec: np.ndarray   # (3,1)
    R:   np.ndarray    # (3,3) rotation matrix

def _marker_object_points(side: float) -> np.ndarray:
    """
    Corner 3D del marker nel suo frame: ordine tl, tr, br, bl (ArUco).
    Lato = side (metri).
    """
    h = side * 0.5
    return np.array(
        [[-h,  h, 0],
         [ h,  h, 0],
         [ h, -h, 0],
         [-h, -h, 0]], dtype=np.float32
    )

def solve_marker_pose_ippe_single(K: np.ndarray, dist: np.ndarray,
                                  corners_i: np.ndarray, side: float) -> Tuple[np.ndarray, np.ndarray]:
    """
    Stima robusta della posa con SOLVEPNP_IPPE_SQUARE e selezione della soluzione
    a minor errore. Fallback EPNP se necessario.
    Returns:
        rvec (3,1), tvec (3,1)
    """
    objp = _marker_object_points(side)
    ok, rvecs_i, tvecs_i, errs = cv.solvePnPGeneric(
        objp, corners_i.reshape(4,1,2), K, dist, flags=cv.SOLVEPNP_IPPE_SQUARE
    )
    if not ok or len(rvecs_i) == 0:
        ok2, rv, tv = cv.solvePnP(objp, corners_i.reshape(4,1,2), K, dist, flags=cv.SOLVEPNP_EPNP)
        return rv.reshape(3,1), tv.reshape(3,1)

    j = int(np.argmin(np.array(errs).reshape(-1)))
    return rvecs_i[j], tvecs_i[j]

def estimate_marker_poses(detections, K: np.ndarray, dist: np.ndarray, marker_size: float) -> List[MarkerPose]:
    """
    Stima la posa (rvec, tvec, R) per ogni MarkerDetection.
    """
    poses: List[MarkerPose] = []
    for det in detections:
        rvec, tvec = solve_marker_pose_ippe_single(K, dist, det.corners, marker_size)
        R, _ = cv.Rodrigues(rvec)
        poses.append(MarkerPose(det.id, rvec, tvec, R))
    return poses
