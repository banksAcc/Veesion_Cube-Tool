# pc/app/algo/api.py
from typing import Dict, Any, Optional, Mapping, List
import numpy as np
import cv2 as cv

from .detect import detect_markers
from .pnp import estimate_marker_poses
from .geometry import average_poses, quat_from_R
from .viz import draw_sphere_overlay, draw_detected_markers

# Mappa ID Marker -> ID Faccia (omessa per brevità, è la stessa di prima)
DEFAULT_MARKER_MAP = {
    1: "H5", 2: "H2", 3: "P0", 4: "H3", 5: "H0", 6: "H6", 7: "P2", 8: "P8", 
    10: "H8", 9: "H4", 11: "P1", 12: "H9", 13: "P7", 14: "P6", 15: "H15", 
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
    min_marker_area_px: float = 150.0,
    weight_exponent: float = 1,
    outlier_distance_threshold: float = 0,
    return_overlay: bool = False,
    timestamp: Optional[float] = None,
    marker_map: Dict[int, str] = DEFAULT_MARKER_MAP
) -> Dict[str, Any]:

    # 1. Rilevamento
    detections = detect_markers(image, aruco_dict)
    
    if detections:
        gray = cv.cvtColor(image, cv.COLOR_BGR2GRAY)
        criteria = (cv.TERM_CRITERIA_EPS + cv.TERM_CRITERIA_MAX_ITER, 30, 0.001)
        for det in detections:
            cv.cornerSubPix(gray, det.corners, (5, 5), (-1, -1), criteria)

    # 2. Filtro Area
    valid_detections = [d for d in detections if d.area_px >= min_marker_area_px]
    
    if not valid_detections:
        raise ValueError("Nessun marker valido trovato.")

    # 3. PnP
    poses = estimate_marker_poses(valid_detections, K, dist, marker_size)
    if not poses:
        raise ValueError("PnP fallito.")

    # 4. Preparazione Candidati (Primari e Alternativi Flippati)
    body_poses_candidates = []
    alternatives_forced = [] # Qui mettiamo la soluzione con Z invertita
    weights = []
    valid_marker_info = []
    
    # Dati grezzi per debug (Centri calcolati geometricamente)
    # Li calcoliamo entrambi per ogni marker: Normal (Red) e Flipped (Green)
    debug_centers_normal = [] 
    debug_centers_flipped = []

    GEO_RADIUS = 0.05678 

    for det, m_pose in zip(valid_detections, poses):
        face_id = marker_map.get(det.id)
        if face_id and face_id in transforms:
            T_face_body = transforms[face_id]
            
            # --- A. Soluzione Primaria ---
            T_cam_marker = np.eye(4)
            T_cam_marker[:3, :3] = m_pose.R
            T_cam_marker[:3, 3] = m_pose.tvec.flatten()
            
            T_cam_body = T_cam_marker @ T_face_body
            body_poses_candidates.append(T_cam_body)
            
            # --- B. Soluzione Alternativa (Flip Z Esplicito) ---
            # Calcoliamo la trasformazione allo stesso modo, ma invertiamo manualmente gli assi
            T_cam_marker_flip = np.eye(4)
            
            # Copiamo la rotazione originale per modificarla
            R_flipped = m_pose.R.copy()
            
            # Invertiamo l'asse Z (colonna 2) come richiesto.
            # ATTENZIONE: Per mantenere la matrice una rotazione valida (determinante +1)
            # e non trasformarla in una riflessione, dobbiamo invertire anche l'asse Y (colonna 1).
            # Questo è geometricamente equivalente a ruotare il marker di 180° su se stesso.
            R_flipped[:, 1] *= -1 # Invertiamo Y
            R_flipped[:, 2] *= -1 # Invertiamo Z <--- Flip Z
            
            T_cam_marker_flip[:3, :3] = R_flipped
            T_cam_marker_flip[:3, 3] = m_pose.tvec.flatten() # La posizione del marker non cambia
            
            T_cam_body_flip = T_cam_marker_flip @ T_face_body
            alternatives_forced.append(T_cam_body_flip)
            
            # Peso
            weights.append(det.area_px)
            
            # --- C. Calcolo Centri Geometrici per Debug (Visualizzazione) ---
            # 1. Normale: Centro = T - Z * Raggio
            z_axis = m_pose.R[:, 2]
            center_normal = m_pose.tvec.flatten() - (z_axis * GEO_RADIUS)
            debug_centers_normal.append(center_normal)
            
            # 2. Flippato: Centro = T + Z * Raggio (Opposto)
            # (Matematicamente equivalente a usare R_flipped che ha -Z)
            center_flipped = m_pose.tvec.flatten() + (z_axis * GEO_RADIUS)
            debug_centers_flipped.append(center_flipped)

            valid_marker_info.append({
                "id": det.id,
                "face": face_id,
                "rvec": m_pose.rvec.flatten().tolist(),
                "tvec": m_pose.tvec.flatten().tolist(),
                "area_px": det.area_px 
            })
        else:
            # Marker non mappato nel JSON
            alternatives_forced.append(None)
            debug_centers_normal.append(None)
            debug_centers_flipped.append(None)

    if not body_poses_candidates:
        raise ValueError("Nessun marker corrisponde a facce note.")

    # 5. Media e Selezione (con la tua logica custom)
    T_final, flipped_indices = average_poses(
        body_poses_candidates, 
        weights=weights,
        alternatives_4x4=alternatives_forced, # Passiamo i flip forzati
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
        # Costruiamo la lista finale da visualizzare (logica invariata)
        centers_to_draw_red = []
        centers_to_draw_green = []
        
        for i in range(len(body_poses_candidates)):
            if debug_centers_normal[i] is None:
                centers_to_draw_red.append(None)
                centers_to_draw_green.append(None)
                continue
                
            if i in flipped_indices:
                centers_to_draw_green.append(debug_centers_flipped[i])
                centers_to_draw_red.append(None)
            else:
                centers_to_draw_red.append(debug_centers_normal[i])
                centers_to_draw_green.append(None)

        # Chiamata alla funzione aggiornata (che ora disegna SOLO box e pallini, NIENTE assi locali)
        debug_img = draw_detected_markers(
            image, 
            valid_detections, 
            poses, 
            K, 
            dist, 
            marker_size/2,
            red_centers=centers_to_draw_red,    
            green_centers=centers_to_draw_green 
        )

        # --- CALCOLO SHIFT SOLO PER GLI ASSI ---
        Z_SHIFT = 0.17  # 15 cm
        local_z_axis = R_final[:, 2] # Asse Z locale
        
        # Calcoliamo dove disegnare gli assi: Centro - (Z * 0.15)
        t_axes_shifted = t_final - (local_z_axis * Z_SHIFT)

        # Sfera Globale + ASSI DEL CORPO
        # rvec_final e tvec_final contengono la posa media del corpo solido.
        # Viz.py ora userà questi per disegnare la terna d'assi XYZ globale
        overlay_img = draw_sphere_overlay(
            img=debug_img, 
            K=K, 
            dist=dist, 
            rvec=rvec_final, 
            tvec=t_final,          # <--- La sfera resta al centro (t_final)
            radius=GEO_RADIUS,
            color=(0, 0, 255),
            alpha=0.2,
            tvec_axes=t_axes_shifted # <--- Gli assi vengono disegnati shiftati
        )
        dist_cm = np.linalg.norm(t_final) * 100
        n_flipped = len(flipped_indices)
        label = f"D:{dist_cm:.1f}cm | N:{len(body_poses_candidates)} | Flip:{n_flipped}"
        cv.putText(overlay_img, label, (20, 50), cv.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    return {
        "rvec": rvec_final,
        "tvec": t_final,
        "R": R_final,
        "quat": quat_final,
        "num_markers": len(body_poses_candidates),
        "markers": valid_marker_info,
        "overlay": overlay_img,
        "filter_debug": {} 
    }