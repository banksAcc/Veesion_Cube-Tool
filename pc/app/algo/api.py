# pc/app/algo/api.py
from typing import Dict, Any, Optional, Mapping, List
import numpy as np
import cv2 as cv

from .detect import detect_markers
from .pnp import estimate_marker_poses
from .geometry import average_poses, quat_from_R
from .viz import draw_sphere_overlay, draw_detected_markers

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
    # --- Parametri di Tuning Stabilità ---
    min_marker_area_px: float = 150.0,       # Soglia dimensione minima (step 2)
    weight_exponent: float = 1,            # Esponente per peso area (step 4)
    outlier_distance_threshold: float = 0, # Metri per scartare outlier (step 4)
    # -------------------------------------
    return_overlay: bool = False,
    timestamp: Optional[float] = None,       # Mantenuto per compatibilità interfaccia, ma inutilizzato
    marker_map: Dict[int, str] = DEFAULT_MARKER_MAP
) -> Dict[str, Any]:

        
    # 1. Rilevamento 2D
    detections = detect_markers(image, aruco_dict)
    
    # --- 1b. Refinement Sub-Pixel ---
    # Fondamentale per avere pose stabili. Affina i corner trovati.
    if detections:
        gray = cv.cvtColor(image, cv.COLOR_BGR2GRAY)
        criteria = (cv.TERM_CRITERIA_EPS + cv.TERM_CRITERIA_MAX_ITER, 30, 0.001)
        for det in detections:
            cv.cornerSubPix(gray, det.corners, (5, 5), (-1, -1), criteria)

    # 2. Filtro Area
    # Scartiamo i marker troppo piccoli (rumorosi) PRIMA del PnP
    valid_detections = [d for d in detections if d.area_px >= min_marker_area_px]
    
    if not valid_detections:
        raise ValueError("Nessun marker valido trovato (filtro area o nessun rilevamento).")

    # 3. Stima Posa Marker (PnP)
    # NESSUNA logica anti-flip o filtri temporali qui. 
    # Ci fidiamo del solver in pnp.py e della media robusta successiva.
    poses = estimate_marker_poses(valid_detections, K, dist, marker_size)

    if not poses:
        raise ValueError("PnP fallito su tutti i marker.")

    # 4. Calcolo Posa del Corpo e Raccolta Pesi
    body_poses_candidates = []
    weights = []
    valid_marker_info = []

    for det, m_pose in zip(valid_detections, poses):
        face_id = marker_map.get(det.id)
        if face_id and face_id in transforms:
            T_face_body = transforms[face_id]
            
            # Posa del Marker rispetto alla Camera
            T_cam_marker = np.eye(4)
            T_cam_marker[:3, :3] = m_pose.R
            T_cam_marker[:3, 3] = m_pose.tvec.flatten()
            
            # Posa del Corpo: T_cam_body = T_cam_marker * T_face_body
            T_cam_body = T_cam_marker @ T_face_body
            
            body_poses_candidates.append(T_cam_body)
            
            # Peso base = Area in pixel
            weights.append(det.area_px) 
            
            valid_marker_info.append({
                "id": det.id,
                "face": face_id,
                "rvec": m_pose.rvec.flatten().tolist(),
                "tvec": m_pose.tvec.flatten().tolist(),
                "area_px": det.area_px 
            })

    if not body_poses_candidates:
        raise ValueError("Nessun marker rilevato corrisponde a facce note nel JSON.")

    # 5. Media PESATA ROBUSTA
    # Usa la nuova funzione in geometry.py che supporta pesi esponenziali e rimozione outlier
    T_final = average_poses(
        body_poses_candidates, 
        weights=weights,
        weight_exponent=weight_exponent,
        outlier_distance_threshold=outlier_distance_threshold
    )
    
    R_final = T_final[:3, :3]
    t_final = T_final[:3, 3]
    rvec_final, _ = cv.Rodrigues(R_final)
    quat_final = quat_from_R(R_final)

    # 6. Overlay
    overlay_img = None
    if return_overlay:
        # Disegna i box e gli ID dei marker usati
        debug_img = draw_detected_markers(image, valid_detections, poses, K, dist, marker_size/2)
        
        # Disegna la Sfera Rossa (Posa Finale calcolata)
        sphere_radius = 0.057 # Raggio stimato sfera (da aggiustare sul tuo oggetto reale)
        overlay_img = draw_sphere_overlay(
            img=debug_img, 
            K=K, 
            dist=dist, 
            rvec=rvec_final, 
            tvec=t_final, 
            radius=sphere_radius,
            color=(0, 0, 255), # Rosso
            alpha=0.2          # Trasparenza
        )

        # Info a schermo
        dist_cm = np.linalg.norm(t_final) * 100
        label = f"Dist: {dist_cm:.1f}cm | Mkrs: {len(body_poses_candidates)} | Exp: {weight_exponent}"
        cv.putText(overlay_img, label, (20, 50), cv.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)


    return {
        "rvec": rvec_final,
        "tvec": t_final,
        "R": R_final,
        "quat": quat_final,
        "num_markers": len(body_poses_candidates),
        "markers": valid_marker_info,
        "overlay": overlay_img,
        # filter_debug vuoto perché abbiamo rimosso il filtro temporale
        "filter_debug": {} 
    }