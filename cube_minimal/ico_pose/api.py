"""Pose estimation for the truncated icosahedron instrumented with ArUco markers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import cv2 as cv
import numpy as np

# Import relativi al tuo pacchetto
from ..cube_pose.aruco_detect import MarkerDetection, detect_markers
from ..cube_pose.camera_io import load_camera
from ..cube_pose.filtering.marker_filter import MarkerFilter, MarkerFilterResult
from ..cube_pose.marker_pose import MarkerPose, estimate_marker_poses
from ..cube_pose.cube_pose import _quat_from_R
from ..cube_pose.viz import draw_marker_outline, draw_small_axes


# Mapping aggiornato
MARKER_TO_FACE_MAP: Mapping[int, str] = {
    1: "H5", 2: "H2", 3: "P0", 4: "H3", 5: "H0", 6: "H6", 7: "P2", 8: "P8", 
    9: "H8", 10: "H4", 11: "P1", 12: "H9", 13: "P7", 14: "P6", 15: "H15", 
    16: "P4", 17: "H1", 18: "H7", 19: "H14", 20: "H17", 21: "H19", 22: "P3", 
    23: "H13", 24: "P11", 25: "P5", 26: "P10", 27: "H10", 28: "H16", 
    29: "H11", 30: "H18", 31: "H12",
}


@dataclass
class IcoPose:
    """Pose of the truncated icosahedron in the camera frame."""
    R: np.ndarray
    t: np.ndarray
    rvec: np.ndarray
    quat: np.ndarray
    num_markers: int


@dataclass
class _BodyPoseCandidate:
    detection: MarkerDetection
    marker_pose: MarkerPose
    body_pose: np.ndarray
    face_id: str


_def_transform_cache: Optional[Dict[str, np.ndarray]] = None

# Cache per i punti 3D della sfera (Punti, Indici Linee)
_SPHERE_CACHE: Optional[Tuple[np.ndarray, List[List[int]]]] = None


def _load_transforms(path: Optional[Path]) -> Dict[str, np.ndarray]:
    """Carica le trasformazioni Face->Body gestendo vari percorsi."""
    global _def_transform_cache
    data = {}
    
    if path is None:
        if _def_transform_cache is None:
            try:
                # Prova a caricare dal package
                with resources.open_text(__package__, "transforms_face_to_body.json", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                # Fallback per esecuzione locale/test
                local_path = Path("transforms_face_to_body.json")
                if local_path.exists():
                    with open(local_path, "r") as f: data = json.load(f)
                else:
                    # Ultimo tentativo: cerca nella cartella dell'app
                    app_path = Path("pc/app/transforms_face_to_body.json")
                    if app_path.exists():
                        with open(app_path, "r") as f: data = json.load(f)
                    else:
                        # Se fallisce tutto, ritorna dizionario vuoto (o raise error)
                        raise FileNotFoundError("transforms_face_to_body.json non trovato.")
            
            _def_transform_cache = {k: np.asarray(v, dtype=float) for k, v in data.items()}
        return dict(_def_transform_cache)

    with Path(path).open("r", encoding="utf-8") as f:
        data = json.load(f)
    return {k: np.asarray(v, dtype=float) for k, v in data.items()}


def _compose_body_pose(marker_pose: MarkerPose, face_transform: np.ndarray) -> np.ndarray:
    T_cam_marker = np.eye(4, dtype=float)
    T_cam_marker[:3, :3] = marker_pose.R
    T_cam_marker[:3, 3] = marker_pose.tvec.reshape(3,)
    return T_cam_marker @ face_transform


def _average_poses(poses: Sequence[np.ndarray]) -> np.ndarray:
    if not poses:
        raise ValueError("Cannot average an empty list of poses.")

    translations = np.array([T[:3, 3] for T in poses])
    avg_translation = np.mean(translations, axis=0)

    rotations = np.mean([T[:3, :3] for T in poses], axis=0)
    U, _, Vt = np.linalg.svd(rotations)
    avg_rotation = U @ Vt
    if np.linalg.det(avg_rotation) < 0:
        U[:, -1] *= -1
        avg_rotation = U @ Vt

    T_avg = np.eye(4, dtype=float)
    T_avg[:3, :3] = avg_rotation
    T_avg[:3, 3] = avg_translation
    return T_avg


def _filter_and_project_candidates(
    detections: Sequence[MarkerDetection],
    poses: Sequence[MarkerPose],
    transform_map: Mapping[str, np.ndarray],
    marker_to_face: Mapping[int, str],
) -> List[_BodyPoseCandidate]:
    candidates: list[_BodyPoseCandidate] = []
    for det, pose in zip(detections, poses):
        face_id = marker_to_face.get(det.id)
        if face_id is None:
            continue
        face_tf = transform_map.get(face_id)
        if face_tf is None:
            continue
        body_pose = _compose_body_pose(pose, face_tf)
        candidates.append(_BodyPoseCandidate(det, pose, body_pose, face_id))
    return candidates


# =========================================================
#  FUNZIONI DI DISEGNO (SFERA + OVERLAY)
# =========================================================

def _get_sphere_geometry(radius: float, rings: int = 12, sectors: int = 20):
    """Genera e cacha i punti 3D della sfera."""
    global _SPHERE_CACHE
    
    if _SPHERE_CACHE is not None:
        pts_unit, lines = _SPHERE_CACHE
        # Restituiamo i punti scalati per il raggio attuale
        return pts_unit * radius, lines

    points = []
    lines_indices = []
    
    # Vertici
    for i in range(rings + 1):
        theta = i * np.pi / rings
        for j in range(sectors):
            phi = j * 2 * np.pi / sectors
            x = np.sin(theta) * np.cos(phi)
            y = np.sin(theta) * np.sin(phi)
            z = np.cos(theta)
            points.append([x, y, z])

    points_unit = np.array(points, dtype=np.float32)

    # Indici Linee (Grid Topology)
    # Paralleli
    for i in range(rings + 1):
        ring_line = []
        for j in range(sectors):
            ring_line.append(i * sectors + j)
        ring_line.append(i * sectors) # Chiudi anello
        lines_indices.append(ring_line)

    # Meridiani
    for j in range(sectors):
        meridian_line = []
        for i in range(rings + 1):
            meridian_line.append(i * sectors + j)
        lines_indices.append(meridian_line)

    _SPHERE_CACHE = (points_unit, lines_indices)
    return points_unit * radius, lines_indices


def _draw_sphere_wireframe(img, K, dist, rvec, tvec, radius=0.058):
    """Disegna sfera wireframe proiettata."""
    try:
        points_3d, lines_indices = _get_sphere_geometry(radius)
        img_pts_float, _ = cv.projectPoints(points_3d, rvec, tvec, K, dist)
        img_pts = img_pts_float.reshape(-1, 2).astype(np.int32)
        
        h, w = img.shape[:2]
        
        # Disegna solo le linee che sono (almeno parzialmente) nel frame
        for line_idx in lines_indices:
            pts = img_pts[line_idx]
            # Semplice check di visibilità per evitare errori grafici gravi
            if np.any((pts[:,0] >= 0) & (pts[:,0] < w) & (pts[:,1] >= 0) & (pts[:,1] < h)):
                cv.polylines(img, [pts], isClosed=False, color=(255, 100, 0), thickness=1, lineType=cv.LINE_AA)
    except Exception:
        pass


def _make_overlay(
    image: np.ndarray,
    K: np.ndarray,
    dist: np.ndarray,
    rvec_body: np.ndarray,
    tvec_body: np.ndarray,
    candidates: Sequence[_BodyPoseCandidate],
    axis_length: float,
) -> np.ndarray:
    overlay = image.copy()

    # 1. Disegno outline marker rilevati
    for cand in candidates:
        try:
            draw_marker_outline(overlay, cand.detection.corners, (0, 255, 255), 2)
        except Exception:
            pass

    # 2. Disegno SFERA (Raggio 0.058m = 58mm)
    _draw_sphere_wireframe(overlay, K, dist, rvec_body, tvec_body, radius=0.058)

    # 3. Disegno PUNTO CENTRALE (Rosso)
    try:
        center_pt = np.array([[0.0, 0.0, 0.0]], dtype=float)
        img_pts, _ = cv.projectPoints(center_pt, rvec_body, tvec_body, K, dist)
        cx, cy = img_pts[0].ravel().astype(int)
        
        h, w = overlay.shape[:2]
        if 0 <= cx < w and 0 <= cy < h:
            cv.circle(overlay, (cx, cy), 5, (0, 0, 255), -1) # Rosso
            cv.circle(overlay, (cx, cy), 6, (255, 255, 255), 1) # Bianco
            
            # Info distanza in cm
            dist_m = np.linalg.norm(tvec_body)
            cv.putText(overlay, f"{dist_m*100:.1f}cm", (cx+10, cy), 
                       cv.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)
    except Exception:
        pass

    # 4. Disegno ASSI DEL CORPO (PICCOLI)
    try:
        # Scale factor 1.0 = Grandezza simile a un marker
        scale_factor = 1.0 
        cv.drawFrameAxes(overlay, K, dist, rvec_body, tvec_body, axis_length * scale_factor, 2)
    except Exception:
        pass

    return overlay


def estimate_truncated_ico_from_image(
    image_or_path: Any,
    camera_npz: str,
    aruco_dict: str,
    marker_size: float, # DEVE ESSERE IN METRI (es. 0.021)
    transform_path: Optional[Path] = None,
    marker_to_face: Mapping[int, str] = MARKER_TO_FACE_MAP,
    return_overlay: bool = False,
    marker_filter: Optional[MarkerFilter] = None,
    timestamp: Optional[float] = None,
) -> Dict[str, Any]:
    
    # --- Input Handling ---
    if isinstance(image_or_path, str):
        img = cv.imread(image_or_path)
        if img is None: raise FileNotFoundError(f"{image_or_path}")
    else:
        img = image_or_path
        if (img is None or not isinstance(img, np.ndarray) or img.ndim != 3):
            raise ValueError("Input must be image path or BGR np.ndarray.")

    # --- Pipeline ---
    K, dist = load_camera(camera_npz)

    detections = detect_markers(img, aruco_dict)
    if len(detections) == 0:
        raise ValueError("No markers detected.")

    poses = estimate_marker_poses(detections, K, dist, marker_size)

    if marker_filter:
        res = marker_filter.apply(detections, poses, timestamp=timestamp)
        detections, poses = res.detections, res.poses

    transforms = _load_transforms(Path(transform_path) if transform_path else None)
    
    candidates = _filter_and_project_candidates(detections, poses, transforms, marker_to_face)
    if not candidates:
        raise ValueError("No valid faces found.")

    # Media Pose
    T_avg = _average_poses([c.body_pose for c in candidates])
    R_avg = T_avg[:3, :3]
    t_avg = T_avg[:3, 3]
    rvec_avg, _ = cv.Rodrigues(R_avg)
    quat = _quat_from_R(R_avg)

    # Overlay
    overlay = None
    if return_overlay:
        # Passiamo axis_length uguale al marker_size (es. 0.021m)
        overlay = _make_overlay(img, K, dist, rvec_avg, t_avg, candidates, marker_size)

    # Output Construction
    marker_dicts = []
    for cand in candidates:
        marker_dicts.append({
            "id": int(cand.marker_pose.id),
            "face": cand.face_id,
            "rvec": cand.marker_pose.rvec.reshape(3).tolist(),
            "tvec": cand.marker_pose.tvec.reshape(3).tolist(),
            "R": cand.marker_pose.R.tolist(),
        })

    filter_debug = {
        "discarded_ids": filter_result.discarded_ids if marker_filter and (filter_result := locals().get('res')) else [],
        "corrected_ids": filter_result.corrected_ids if marker_filter and (filter_result := locals().get('res')) else [],
    }

    return {
        "tvec": t_avg,
        "rvec": rvec_avg,
        "R": R_avg,
        "quat": quat,
        "num_markers": len(candidates),
        "markers": marker_dicts,
        "overlay": overlay,
        "marker_filter": filter_debug,
    }


__all__ = ["estimate_truncated_ico_from_image", "MARKER_TO_FACE_MAP", "IcoPose"]