# pc/app/algo/pnp.py
import cv2 as cv
import numpy as np
from dataclasses import dataclass
from typing import List, Optional
from .detect import MarkerDetection

@dataclass
class MarkerPose:
    id: int
    rvec: np.ndarray 
    tvec: np.ndarray
    R: np.ndarray    
    reproj_err: float
    # --- Dati per la soluzione alternativa (Flip) ---
    alt_rvec: Optional[np.ndarray] = None
    alt_tvec: Optional[np.ndarray] = None
    alt_R: Optional[np.ndarray] = None

def _get_marker_object_points(side_length: float) -> np.ndarray:
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
    
    # --- OPZIONI FLAG DISPONIBILI PER IL SOLVER ---
    # Cambia la flag qui sotto in base alle necessità:
    
    # 1. cv.SOLVEPNP_IPPE_SQUARE (Default attuale)
    #    Specifico per marker quadrati piani. Molto preciso.
    #    Restituisce multiple soluzioni (ambiguità), qui prendiamo la prima.
    
    # 2. cv.SOLVEPNP_SQPNP 
    #    (Richiede OpenCV >= 4.5.3). Algoritmo "Square-Root PnP".
    #    Tende a trovare il minimo globale ed è molto stabile contro i flip.
    #    Se lo usi, restituisce di solito una sola soluzione ottima.
    
    # 3. cv.SOLVEPNP_ITERATIVE
    #    Metodo classico (Levenberg-Marquardt). Robusto ma può bloccarsi in minimi locali.
    #    Buono se hai una "guess" iniziale (qui non la usiamo).
    
    # Seleziona qui l'algoritmo:
    
    # IPPE_SQUARE è necessario per avere le 2 soluzioni analitiche
    solver_flag = cv.SOLVEPNP_IPPE_SQUARE  

    for det in detections:
        # solvePnPGeneric restituisce vettori di soluzioni (di solito 2 per IPPE)
        ok, rvecs, tvecs, errs = cv.solvePnPGeneric(
            obj_points, 
            det.corners.reshape(4, 1, 2), 
            K, 
            dist, 
            flags=solver_flag
        )
        
        if ok and len(rvecs) > 0:
            # 1. Soluzione Primaria (Index 0 - Minor errore riproiezione)
            rvec_0, tvec_0 = rvecs[0], tvecs[0]
            err_0 = errs[0].item() if (errs is not None and len(errs) > 0) else 0.0
            R_0, _ = cv.Rodrigues(rvec_0)
            
            # 2. Soluzione Alternativa (Index 1 - Il possibile "Flip")
            alt_rvec, alt_tvec, alt_R = None, None, None
            if len(rvecs) > 1:
                alt_rvec = rvecs[1]
                alt_tvec = tvecs[1]
                alt_R, _ = cv.Rodrigues(alt_rvec)
            
            poses.append(MarkerPose(
                id=det.id, 
                rvec=rvec_0, tvec=tvec_0, R=R_0, reproj_err=err_0,
                alt_rvec=alt_rvec, alt_tvec=alt_tvec, alt_R=alt_R
            ))
            
    return poses