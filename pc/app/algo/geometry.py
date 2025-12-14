# pc/app/algo/geometry.py
import numpy as np
import cv2 as cv
from typing import List, Optional

def quat_from_R(R: np.ndarray) -> np.ndarray:
    """Converte matrice di rotazione 3x3 in Quaternione (w, x, y, z)."""
    tr = np.trace(R)
    if tr > 0:
        S = np.sqrt(tr + 1.0) * 2
        w = 0.25 * S
        x = (R[2,1] - R[1,2]) / S
        y = (R[0,2] - R[2,0]) / S
        z = (R[1,0] - R[0,1]) / S
    else:
        idx = np.argmax([R[0,0], R[1,1], R[2,2]])
        if idx == 0:
            S = np.sqrt(1.0 + R[0,0] - R[1,1] - R[2,2]) * 2
            w = (R[2,1] - R[1,2]) / S
            x = 0.25 * S
            y = (R[0,1] + R[1,0]) / S
            z = (R[0,2] + R[2,0]) / S
        elif idx == 1:
            S = np.sqrt(1.0 + R[1,1] - R[0,0] - R[2,2]) * 2
            w = (R[0,2] - R[2,0]) / S
            x = (R[0,1] + R[1,0]) / S
            y = 0.25 * S
            z = (R[1,2] + R[2,1]) / S
        else:
            S = np.sqrt(1.0 + R[2,2] - R[0,0] - R[1,1]) * 2
            w = (R[1,0] - R[0,1]) / S
            x = (R[0,2] + R[2,0]) / S
            y = (R[1,2] + R[2,1]) / S
            z = 0.25 * S     
    return np.array([w, x, y, z])

def _compute_mean_pose(poses: List[np.ndarray], weights: np.ndarray) -> np.ndarray:
    """Helper interno per calcolare la media pesata."""
    w_sum = np.sum(weights)
    norm_weights = (weights / w_sum) if w_sum > 1e-6 else (np.ones(len(weights))/len(weights))

    # Traslazione
    translations = np.array([P[:3, 3] for P in poses])
    t_mean = np.average(translations, axis=0, weights=norm_weights)
    
    # Rotazione (Media matrici + SVD)
    R_sum = np.zeros((3, 3))
    for i, P in enumerate(poses):
        R_sum += P[:3, :3] * norm_weights[i]
        
    U, _, Vt = np.linalg.svd(R_sum)
    R_mean = U @ Vt
    
    # Fix riflessione
    if np.linalg.det(R_mean) < 0:
        U[:, -1] *= -1
        R_mean = U @ Vt
        
    T_out = np.eye(4)
    T_out[:3, :3] = R_mean
    T_out[:3, 3] = t_mean
    return T_out

def average_poses(
    poses_4x4: List[np.ndarray], 
    weights: Optional[List[float]] = None,
    # Aggiungiamo le alternative per gestire il FLIP
    alternatives_4x4: Optional[List[Optional[np.ndarray]]] = None, 
    weight_exponent: float = 2.0,
    outlier_distance_threshold: Optional[float] = None
) -> np.ndarray:
    """
    Calcola la media pesata gestendo outlier e correzione flip (Z-invertita).
    Include LOGGING su console per debug.
    """
    if not poses_4x4:
        raise ValueError("Lista pose vuota.")
    
    n = len(poses_4x4)
    if weights is None:
        raw_weights = np.ones(n)
    else:
        raw_weights = np.array(weights, dtype=float)

    # 1. Pesi non lineari
    raw_weights = np.maximum(raw_weights, 1e-3) 
    proc_weights = np.power(raw_weights, weight_exponent)

    # 2. Media Provvisoria (sui candidati primari)
    T_avg_prov = _compute_mean_pose(poses_4x4, proc_weights)

    if outlier_distance_threshold is None:
        return T_avg_prov

    # --- LOGGING DEBUG INIZIO ---
    t_prov = T_avg_prov[:3, 3]
    print(f"\n[AVG] Markers: {n} | Prov Mean: {t_prov[0]:.2f}, {t_prov[1]:.2f}, {t_prov[2]:.2f}")
    
    final_poses = []
    final_weights = []
    
    # 3. Analisi Outlier & Flip Recovery
    for i in range(n):
        P_prim = poses_4x4[i]
        weight = proc_weights[i]
        raw_w = raw_weights[i]
        
        # Calcolo distanze
        dist_prim = np.linalg.norm(P_prim[:3, 3] - t_prov)
        
        status = "UNKNOWN"
        
        # A. Check Primaria
        if dist_prim <= outlier_distance_threshold:
            final_poses.append(P_prim)
            final_weights.append(weight)
            status = f"KEEP (Prim) D={dist_prim:.3f}"
            
        # B. Check Alternativa (Flip)
        elif alternatives_4x4 is not None and alternatives_4x4[i] is not None:
            P_alt = alternatives_4x4[i]
            dist_alt = np.linalg.norm(P_alt[:3, 3] - t_prov)
            
            if dist_alt <= outlier_distance_threshold:
                # SUCCESSO: Abbiamo recuperato un marker flippato!
                final_poses.append(P_alt)
                final_weights.append(weight)
                status = f"!!! FLIP FIXED !!! D={dist_alt:.3f} (was {dist_prim:.3f})"
            else:
                status = f"DROP (Both Bad) Prim={dist_prim:.3f} Alt={dist_alt:.3f}"
        else:
            status = f"DROP (Outlier) D={dist_prim:.3f}"

        # Stampa riga per ogni marker
        print(f"  > [{i}] Area:{int(raw_w):04d} | {status}")

    # Fallback se abbiamo scartato tutto
    if not final_poses:
        print("  [AVG] WARNING: All markers dropped! Fallback to provisional.")
        return T_avg_prov

    # 4. Media Finale
    T_final = _compute_mean_pose(final_poses, np.array(final_weights))
    
    return T_final