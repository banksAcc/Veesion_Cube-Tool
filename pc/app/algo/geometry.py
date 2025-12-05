# pc/app/algo/geometry.py
import numpy as np
import cv2 as cv

def quat_from_R(R: np.ndarray) -> np.ndarray:
    """Converte matrice di rotazione 3x3 in Quaternione (w, x, y, z)."""
    # Implementazione robusta (simile a quella che avevi) o usando scipy se disponibile.
    # Qui uso una versione semplificata basata sulla traccia per brevità, 
    # ma per produzione è meglio la tua versione originale più lunga o scipy.
    tr = np.trace(R)
    if tr > 0:
        S = np.sqrt(tr + 1.0) * 2
        w = 0.25 * S
        x = (R[2,1] - R[1,2]) / S
        y = (R[0,2] - R[2,0]) / S
        z = (R[1,0] - R[0,1]) / S
    else:
        # Fallback per casi numerici instabili (semplificato)
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

def average_poses(poses_4x4: list[np.ndarray]) -> np.ndarray:
    """Calcola la media di N matrici di trasformazione 4x4."""
    if not poses_4x4:
        raise ValueError("Lista pose vuota.")
    
    # Media delle traslazioni (lineare)
    t_mean = np.mean([P[:3, 3] for P in poses_4x4], axis=0)
    
    # Media delle rotazioni (tramite SVD per ortogonalizzazione)
    R_sum = np.mean([P[:3, :3] for P in poses_4x4], axis=0)
    U, _, Vt = np.linalg.svd(R_sum)
    R_mean = U @ Vt
    
    # Correzione determinante (se viene riflessione)
    if np.linalg.det(R_mean) < 0:
        U[:, -1] *= -1
        R_mean = U @ Vt
        
    T_out = np.eye(4)
    T_out[:3, :3] = R_mean
    T_out[:3, 3] = t_mean
    return T_out