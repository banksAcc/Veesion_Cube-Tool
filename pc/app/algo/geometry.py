# pc/app/algo/geometry.py
import numpy as np
import cv2 as cv
from typing import List, Optional, Tuple

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
    if not poses:
        return np.eye(4)

    w_sum = np.sum(weights)
    # Evitiamo divisioni per zero
    norm_weights = (weights / w_sum) if w_sum > 1e-9 else (np.ones(len(weights))/len(weights))

    # Traslazione
    translations = np.array([P[:3, 3] for P in poses])
    t_mean = np.average(translations, axis=0, weights=norm_weights)
    
    # Rotazione (Media matrici + SVD)
    R_sum = np.zeros((3, 3))
    for i, P in enumerate(poses):
        R_sum += P[:3, :3] * norm_weights[i]
        
    U, _, Vt = np.linalg.svd(R_sum)
    R_mean = U @ Vt
    
    # Fix riflessione SVD
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
    alternatives_4x4: Optional[List[Optional[np.ndarray]]] = None, 
    weight_exponent: float = 2.0,
    outlier_distance_threshold: Optional[float] = None
) -> Tuple[np.ndarray, List[int]]:
    """
    Calcola la media pesata in modo ITERATIVO.
    Cerca la combinazione migliore di (Normal/Flipped) che minimizza l'errore globale.
    """
    n = len(poses_4x4)
    if n == 0:
        raise ValueError("Lista pose vuota.")

    # 1. Preparazione Pesi
    if weights is None:
        raw_weights = np.ones(n)
    else:
        raw_weights = np.array(weights, dtype=float)
    
    raw_weights = np.maximum(raw_weights, 1e-3)
    proc_weights = np.power(raw_weights, weight_exponent)

    # Stato corrente: True se usiamo l'alternativa (Flipped), False se usiamo la Primaria
    # Iniziamo tutti come Primari (False)
    current_flip_state = [False] * n
    
    # Lista delle pose correntemente selezionate
    current_poses = [p.copy() for p in poses_4x4]

    MAX_ITER = 10
    print(f"\n[AVG] Starting Iterative Refinement on {n} markers.")

    # --- CICLO DI CONVERGENZA (EM-like) ---
    for it in range(MAX_ITER):
        # A. Calcola Media Corrente
        T_mean = _compute_mean_pose(current_poses, proc_weights)
        t_center = T_mean[:3, 3]
        
        changes_count = 0
        
        # B. Rivaluta ogni marker rispetto alla NUOVA media
        for i in range(n):
            # Se non abbiamo alternative, saltiamo la logica di flip
            if alternatives_4x4 is None or alternatives_4x4[i] is None:
                continue

            # Calcola distanze per le due opzioni
            pose_prim = poses_4x4[i]
            pose_alt = alternatives_4x4[i]
            
            dist_prim = np.linalg.norm(pose_prim[:3, 3] - t_center)
            dist_alt = np.linalg.norm(pose_alt[:3, 3] - t_center)
            
            # Logica decisionale geometrica pura: chi è più vicino al baricentro?
            should_be_flipped = (dist_alt < dist_prim)
            
            # Applica il cambiamento se necessario
            if should_be_flipped != current_flip_state[i]:
                current_flip_state[i] = should_be_flipped
                current_poses[i] = pose_alt if should_be_flipped else pose_prim
                changes_count += 1
        
        # C. Exit condition
        if changes_count == 0:
            print(f"  > Converged at iteration {it}")
            break
    
    # --- FILTRAGGIO FINALE OUTLIER ---
    # Ora che abbiamo la configurazione geometrica più stabile,
    # scartiamo comunque chi è troppo lontano (es. errore di rilevamento vero, non solo flip)
    
    # Ricalcoliamo la media finale stabile
    T_final_candidate = _compute_mean_pose(current_poses, proc_weights)
    t_final = T_final_candidate[:3, 3]
    
    final_poses_for_avg = []
    final_weights_for_avg = []
    final_flipped_indices = []

    print(f"  > Final Check (Threshold: {outlier_distance_threshold})")

    for i in range(n):
        P_curr = current_poses[i]
        w_curr = proc_weights[i]
        is_flipped = current_flip_state[i]
        
        dist_curr = np.linalg.norm(P_curr[:3, 3] - t_final)
        
        status = "DROP"
        
        # Se la soglia è attiva, controlliamo la distanza
        if outlier_distance_threshold is None or outlier_distance_threshold <= 0 or dist_curr <= outlier_distance_threshold:
            final_poses_for_avg.append(P_curr)
            final_weights_for_avg.append(w_curr)
            
            if is_flipped:
                final_flipped_indices.append(i)
                status = "KEEP (Flipped)"
            else:
                status = "KEEP (Normal)"
        
        print(f"    [{i}] D={dist_curr:.3f} | {status}")

    # Fallback: se abbiamo scartato tutti, torniamo la media candidata (meglio di niente)
    if not final_poses_for_avg:
        print("  [AVG] WARNING: All markers rejected by threshold. Returning best guess.")
        return T_final_candidate, [i for i, f in enumerate(current_flip_state) if f]

    # Calcolo definitivo su sottoinsieme pulito
    T_final = _compute_mean_pose(final_poses_for_avg, np.array(final_weights_for_avg))
    
    return T_final, final_flipped_indices