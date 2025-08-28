"""
API di alto livello per stimare la posa del cubo da una singola immagine.
"""

from typing import Dict, Any, Union
import os
import numpy as np
import cv2 as cv

from .camera_io import load_camera
from .aruco_detect import detect_markers
from .marker_pose import estimate_marker_poses
from .cube_pose import estimate_cube_pose

def estimate_cube_from_image(
    image_or_path: Union[str, np.ndarray],
    camera_npz: str,
    aruco_dict: str,
    marker_size: float,
    cube_size: float,
    pair_strategy: str = "first",
    return_overlay: bool = False,
    sample_dir: str | None = None,
) -> Dict[str, Any]:
    """
    Stima la posa del cubo a partire da 1 immagine.

    Args:
        image_or_path: path str di un'immagine o array BGR (H,W,3) np.uint8
        camera_npz: path al .npz con intrinseci ('K'/'cameraMatrix') e dist ('dist'/'distCoeffs')
        aruco_dict: es. "4X4_50"
        marker_size: lato marker (metri) — lato del quadrato nero
        cube_size: lato del cubo (metri)
        pair_strategy: "first" (primi due marker) o "max_angle"
        return_overlay: se True, ritorna anche un'immagine BGR con overlay (wireframe/assi)
        sample_dir: cartella opzionale dove cercare l'immagine se il path è relativo

    Returns:
        dict con:
            - 'tvec': (3,) centro del cubo nel frame camera (metri)
            - 'rvec': (3,1) Rodrigues del cubo
            - 'R': (3,3) matrice di rotazione del cubo
            - 'quat': (4,) quaternion (w,x,y,z)
            - 'num_markers': int numero di marker usati
            - 'overlay': img BGR opzionale (se return_overlay=True)
    Raises:
        ValueError se nessun marker viene trovato.
    """
    # Carica immagine
    if isinstance(image_or_path, str):
        path = image_or_path
        if sample_dir and not os.path.isabs(path) and not os.path.exists(path):
            cand = os.path.join(sample_dir, path)
            if os.path.exists(cand):
                path = cand
        img = cv.imread(path)
        if img is None:
            raise ValueError(f"Immagine non leggibile: {path}")
    else:
        img = image_or_path
        if img is None or not isinstance(img, np.ndarray) or img.ndim != 3:
            raise ValueError("image_or_path deve essere path str o BGR np.ndarray (H,W,3).")

    # Camera
    K, dist = load_camera(camera_npz)

    # Detection
    detections = detect_markers(img, aruco_dict)
    if len(detections) == 0:
        raise ValueError("Nessun marker rilevato nell'immagine.")

    # Pose per marker
    poses = estimate_marker_poses(detections, K, dist, marker_size)

    # Posa cubo
    cube = estimate_cube_pose(poses, cube_size, pair_strategy=pair_strategy)

    # Overlay opzionale
    overlay = None
    if return_overlay:
        from .viz import draw_marker_outline, draw_small_axes, draw_wirecube, project_points_camframe
        overlay = img.copy()
        # assi + outline per ogni marker
        for det, mp in zip(detections, poses):
            draw_marker_outline(overlay, det.corners, (0,255,255), 2)
            cv2_len = max(marker_size * 0.5, cube_size * 0.3)  # scala grossolana
            draw_small_axes(overlay, K, dist, mp.rvec, mp.tvec, cv2_len)
        # wireframe cubo
        draw_wirecube(overlay, K, dist, cube.rvec, cube.t, cube_size, color=(0,255,0), thickness=2)

    return {
        "tvec": cube.t,
        "rvec": cube.rvec,
        "R": cube.R,
        "quat": cube.quat,
        "num_markers": len(poses),
        "overlay": overlay,
    }
