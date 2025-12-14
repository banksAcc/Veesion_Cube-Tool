# pc/app/algo/viz.py
import cv2 as cv
import numpy as np
from typing import Tuple

# Cache per i punti della sfera (evita di ricalcolarli a ogni frame)
_SPHERE_CACHE = None

def _get_sphere_geometry(radius: float, rings: int = 10, sectors: int = 10):
    """Genera i punti 3D di una sfera (Latitudine/Longitudine)."""
    global _SPHERE_CACHE
    # Se il raggio cambia drasticamente o non è inizializzato, ricalcola
    if _SPHERE_CACHE is None or _SPHERE_CACHE[0] != radius:
        points = []
        lines_idx = []
        
        # Generazione Vertici
        for i in range(rings + 1):
            theta = i * np.pi / rings # Da 0 a Pi
            for j in range(sectors):
                phi = j * 2 * np.pi / sectors # Da 0 a 2Pi
                
                x = radius * np.sin(theta) * np.cos(phi)
                y = radius * np.sin(theta) * np.sin(phi)
                z = radius * np.cos(theta)
                points.append([x, y, z])
        
        points = np.array(points, dtype=np.float32)
        
        # Generazione Indici Linee (Griglia)
        # Paralleli
        for i in range(rings + 1):
            base = i * sectors
            for j in range(sectors):
                p1 = base + j
                p2 = base + (j + 1) % sectors
                lines_idx.append((p1, p2))
                
        # Meridiani
        for j in range(sectors):
            for i in range(rings):
                p1 = i * sectors + j
                p2 = (i + 1) * sectors + j
                lines_idx.append((p1, p2))
                
        _SPHERE_CACHE = (radius, points, lines_idx)
    
    return _SPHERE_CACHE[1], _SPHERE_CACHE[2]

def draw_sphere_overlay(img: np.ndarray, K: np.ndarray, dist: np.ndarray, 
                        rvec: np.ndarray, tvec: np.ndarray, 
                        radius: float, 
                        color: Tuple[int, int, int] = (0, 0, 255), # Rosso BGR
                        alpha: float = 0.2) -> np.ndarray:
    """
    Disegna una sfera trasparente con wireframe sul frame.
    """
    overlay = img.copy()
    output = img.copy() # Immagine finale su cui fare blending
    
    # 1. Calcolo del centro proiettato
    center_3d = np.array([[0.0, 0.0, 0.0]], dtype=float)
    center_2d_pts, _ = cv.projectPoints(center_3d, rvec, tvec, K, dist)
    cx, cy = center_2d_pts[0].ravel().astype(int)
    
    # 2. Stima del raggio apparente (Proiettiamo un punto sul bordo)
    # Punto a distanza 'radius' lungo l'asse X locale
    edge_3d = np.array([[radius, 0.0, 0.0]], dtype=float)
    edge_2d_pts, _ = cv.projectPoints(edge_3d, rvec, tvec, K, dist)
    ex, ey = edge_2d_pts[0].ravel().astype(int)
    
    # Raggio in pixel (distanza euclidea tra centro e bordo proiettato)
    radius_px = int(np.linalg.norm([ex - cx, ey - cy]))
    
    # Check bounds per evitare crash se la sfera è fuori schermo o enorme
    h, w = img.shape[:2]
    if radius_px > 0 and 0 <= cx < w and 0 <= cy < h:
        
        # --- A. RIEMPIMENTO TRASPARENTE (Semplificato come cerchio 2D) ---
        # Disegniamo un cerchio pieno sul layer overlay
        cv.circle(overlay, (cx, cy), radius_px, color, -1)
        
        # Applichiamo la trasparenza: Output = alpha*Overlay + (1-alpha)*Original
        cv.addWeighted(overlay, alpha, output, 1 - alpha, 0, output)
        
        # --- B. WIREFRAME 3D (Linee reali proiettate) ---
        pts_3d, lines_idx = _get_sphere_geometry(radius)
        pts_2d, _ = cv.projectPoints(pts_3d, rvec, tvec, K, dist)
        pts_2d = pts_2d.reshape(-1, 2).astype(int)
        
        # Colore Wireframe (Un po' più scuro o arancione per contrasto)
        line_color = (color[0], color[1] + 100, color[2]) 
        
        for p1_idx, p2_idx in lines_idx:
            pt1 = tuple(pts_2d[p1_idx])
            pt2 = tuple(pts_2d[p2_idx])
            
            # Disegna solo se dentro l'immagine (ottimizzazione)
            if (0 <= pt1[0] < w and 0 <= pt1[1] < h) or (0 <= pt2[0] < w and 0 <= pt2[1] < h):
                cv.line(output, pt1, pt2, line_color, 1, cv.LINE_AA)

    return output

def draw_detected_markers(img: np.ndarray, detections, poses, K, dist, size):
    """
    Disegna contorni, assi e INFO AREA dei marker rilevati.
    """
    out = img.copy()  
    return out

def draw_detected_markers_1(img: np.ndarray, detections, poses, K, dist, size):
    """
    Disegna contorni, assi e INFO AREA dei marker rilevati.
    """
    out = img.copy()
    for det, pose in zip(detections, poses):
        # 1. Disegna contorno quadrato
        pts = det.corners.reshape((-1, 1, 2)).astype(np.int32)
        cv.polylines(out, [pts], True, (0, 255, 255), 2)
        
        # 2. Disegna gli assi cartesiani locali
        cv.drawFrameAxes(out, K, dist, pose.rvec, pose.tvec, size, 2)
        
        # 3. Scrivi ID e AREA (px) vicino al primo angolo
        # Prende l'angolo in alto a sinistra del marker
        c = det.corners[0]
        x, y = int(c[0]), int(c[1])
        
        # Testo: "ID: 5 | px: 1200"
        label = f"ID:{det.id} px:{int(det.area_px)}"
        
        # Sfondo nero per il testo (per leggibilità)
        (w, h), _ = cv.getTextSize(label, cv.FONT_HERSHEY_PLAIN, 1.2, 1)
        cv.rectangle(out, (x, y - h - 5), (x + w, y + 5), (0, 0, 0), -1)
        
        # Scritta bianca
        cv.putText(out, label, (x, y), cv.FONT_HERSHEY_PLAIN, 1.2, (255, 255, 255), 1, cv.LINE_AA)
        
    return out