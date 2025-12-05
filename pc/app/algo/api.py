# pc/app/algo/api.py
from typing import Dict, Any, Optional, Mapping
import numpy as np
import cv2 as cv

# Import relativi con il punto .
from .detect import detect_markers
from .pnp import estimate_marker_poses
from .filter import MarkerFilter
from .geometry import average_poses, quat_from_R
from .viz import draw_sphere_overlay, draw_detected_markers # <--- AGGIUNTO draw_sphere_overlay

# Mappa ID Marker -> ID Faccia
DEFAULT_MARKER_MAP = {
    1: "H5", 2: "H2", 3: "P0", 4: "H3", 5: "H0", 6: "H6", 7: "P2", 8: "P8", 
    9: "H8", 10: "H4", 11: "P1", 12: "H9", 13: "P7", 14: "P6", 15: "H15", 
    16: "P4", 17: "H1", 18: "H7", 19: "H14", 20: "H17", 21: "H19", 22: "P3", 
    23: "H13", 24: "P11", 25: "P5", 26: "P10", 27: "H10", 28: "H16", 
    29: "H11", 30: "H18", 31: "H12",
}

def estimate_truncated_ico_from_image(
    image: np.ndarray,
    K: np.ndarray,
    dist: np.ndarray,
    transforms: Mapping[str, np.ndarray],
    aruco_dict: str,
    marker_size: float,
    return_overlay: bool = False,
    marker_filter: Optional[MarkerFilter] = None,
    timestamp: Optional[float] = None,
    marker_map: Dict[int, str] = DEFAULT_MARKER_MAP
) -> Dict[str, Any]:
    """
    Stima la posa dell'icosaedro troncato.
    NON esegue I/O su disco. Accetta solo matrici e immagini.
    """
    
    # 1. Rilevamento 2D
    detections = detect_markers(image, aruco_dict)
    if not detections:
        raise ValueError("Nessun marker trovato.")

    # 2. Stima Posa Marker (PnP)
    poses = estimate_marker_poses(detections, K, dist, marker_size)

    # 3. Filtraggio Temporale (Opzionale)
    filter_stats = {}
    if marker_filter:
        detections, poses, stats = marker_filter.apply(detections, poses, timestamp)
        filter_stats = {"discarded": stats.discarded, "corrected": stats.corrected}
    
    if not poses:
        raise ValueError("Tutti i marker sono stati filtrati/scartati.")

    # 4. Calcolo Posa del Corpo (Body) dai singoli Marker
    body_poses_candidates = []
    valid_marker_info = []

    for det, m_pose in zip(detections, poses):
        face_id = marker_map.get(det.id)
        if face_id and face_id in transforms:
            # T_face_to_body: Trasformazione che porta dalla faccia al centro del corpo
            # La carichiamo dal JSON esterno
            T_face_body = transforms[face_id]
            
            # Costruiamo matrice 4x4 del marker rispetto alla camera
            T_cam_marker = np.eye(4)
            T_cam_marker[:3, :3] = m_pose.R
            T_cam_marker[:3, 3] = m_pose.tvec.flatten()
            
            # Posa del corpo rispetto alla camera: T_cam_body = T_cam_marker * T_face_body
            T_cam_body = T_cam_marker @ T_face_body
            
            body_poses_candidates.append(T_cam_body)
            
            valid_marker_info.append({
                "id": det.id,
                "face": face_id,
                "rvec": m_pose.rvec.flatten().tolist(),
                "tvec": m_pose.tvec.flatten().tolist()
            })

    if not body_poses_candidates:
        raise ValueError("Nessun marker rilevato corrisponde a facce note nel JSON.")

    # 5. Media delle pose candidate
    T_final = average_poses(body_poses_candidates)
    
    R_final = T_final[:3, :3]
    t_final = T_final[:3, 3]
    rvec_final, _ = cv.Rodrigues(R_final)
    quat_final = quat_from_R(R_final)

    # 6. Overlay (Aggiornato con Sfera)
    overlay_img = None
    if return_overlay:
        # A. Disegna i marker singoli per debug
        debug_img = draw_detected_markers(image, detections, poses, K, dist, marker_size/2)
        
        # B. Disegna la SFERA ROSSA TRASPARENTE
        # RAGGIO SFERA: Qui devi decidere quanto è grande la sfera reale.
        # L'icosaedro troncato circoscrive una sfera. 
        # Se marker_size è il lato del quadrato nero, il raggio dell'oggetto intero è circa:
        # Raggio approx ≈ 3.5 * marker_size (dipende dalla tua costruzione fisica precisa)
        # Puoi parametrizzarlo o stimarlo qui:
        sphere_radius = 0.057 # Esempio: aggiusta questo valore in base al tuo oggetto reale!
        
        overlay_img = draw_sphere_overlay(
            img=debug_img, 
            K=K, 
            dist=dist, 
            rvec=rvec_final, 
            tvec=t_final, 
            radius=sphere_radius,
            color=(0, 0, 255), # Rosso
            alpha=0.2          # Trasparenza richiesta
        )

        # C. Testo Info
        dist_cm = np.linalg.norm(t_final) * 100
        label = f"Dist: {dist_cm:.1f}cm | Mkrs: {len(body_poses_candidates)}"
        # Aggiungiamo il testo sopra la sfera
        cx, cy = int(image.shape[1]/2), 30
        cv.putText(overlay_img, label, (20, 50), cv.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    return {
        "rvec": rvec_final,
        "tvec": t_final,
        "R": R_final,
        "quat": quat_final,
        "num_markers": len(body_poses_candidates),
        "markers": valid_marker_info,
        "overlay": overlay_img,
        "filter_debug": filter_stats
    }