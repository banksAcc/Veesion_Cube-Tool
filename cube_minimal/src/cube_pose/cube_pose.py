from dataclasses import dataclass
from typing import List, Tuple
import numpy as np
import cv2 as cv

from .marker_pose import MarkerPose

@dataclass
class CubePose:
    """Posa del cubo nel frame camera."""
    R: np.ndarray      # (3,3)
    t: np.ndarray      # (3,)
    rvec: np.ndarray   # (3,1) Rodrigues
    quat: np.ndarray   # (4,) (w,x,y,z)

def _center_from_marker(Rm: np.ndarray, t_marker_cam: np.ndarray, cube_size: float) -> np.ndarray:
    """
    Centro cubo stimato da un singolo marker:
    Z_marker (blu) esce dal piano → centro = t - Z * L/2
    """
    z_marker_cam = Rm[:, 2]
    return t_marker_cam - z_marker_cam * (cube_size * 0.5)

def _quat_from_R(R: np.ndarray) -> np.ndarray:
    """Converte matrice di rotazione in quaternion (w,x,y,z)."""
    t = np.trace(R)
    if t > 0:
        S = np.sqrt(t + 1.0) * 2.0
        w = 0.25 * S
        x = (R[2,1] - R[1,2]) / S
        y = (R[0,2] - R[2,0]) / S
        z = (R[1,0] - R[0,1]) / S
    else:
        i = int(np.argmax([R[0,0], R[1,1], R[2,2]]))
        if i == 0:
            S = np.sqrt(1.0 + R[0,0] - R[1,1] - R[2,2]) * 2.0
            w = (R[2,1] - R[1,2]) / S; x = 0.25 * S
            y = (R[0,1] + R[1,0]) / S; z = (R[0,2] + R[2,0]) / S
        elif i == 1:
            S = np.sqrt(1.0 + R[1,1] - R[0,0] - R[2,2]) * 2.0
            w = (R[0,2] - R[2,0]) / S; x = (R[0,1] + R[1,0]) / S
            y = 0.25 * S; z = (R[1,2] + R[2,1]) / S
        else:
            S = np.sqrt(1.0 + R[2,2] - R[0,0] - R[1,1]) * 2.0
            w = (R[1,0] - R[0,1]) / S; x = (R[0,2] + R[2,0]) / S
            y = (R[1,2] + R[2,1]) / S; z = 0.25 * S
    q = np.array([w,x,y,z], dtype=float)
    return q / (np.linalg.norm(q) + 1e-12)

def estimate_cube_pose(marker_poses: List[MarkerPose], cube_size: float,
                       pair_strategy: str = "first") -> CubePose:
    """
    Stima la posa del cubo (R, t) a partire dalle pose dei marker visibili.

    Strategia orientamento:
      - Se >=2 marker: allinea due facce del cubo a due marker:
            Z_cubo = -Z_marker_1
            X_cubo = proiezione di (-Z_marker_2) sul piano ortogonale a Z_cubo
            Y_cubo = Z × X
        Se pair_strategy == "max_angle" sceglie la coppia con normali più ortogonali.
      - Se 1 marker: usa -Z_marker per Z_cubo e X/Y dal piano della stessa faccia.

    Centro:
      - Media dei centri stimati dai singoli marker: (t_i - Z_i * L/2)

    Returns:
        CubePose(R, t, rvec, quat)
    """
    if len(marker_poses) == 0:
        raise ValueError("Nessun marker per stimare la posa del cubo.")

    # centro: media dei centri per marker
    centers = []
    for m in marker_poses:
        centers.append(_center_from_marker(m.R, m.tvec.reshape(3,), cube_size))
    t_cube = np.mean(np.vstack(centers), axis=0)  # (3,)

    # orientamento
    if len(marker_poses) >= 2:
        # scelta coppia
        if pair_strategy == "max_angle":
            # massimizza l'angolo tra normali
            z_list = [m.R[:,2] for m in marker_poses]
            best = (0, 1, -1.0)  # i,j,score
            for i in range(len(z_list)):
                for j in range(i+1, len(z_list)):
                    score = 1.0 - abs(np.dot(z_list[i], z_list[j]))  # 1 - |cosθ|
                    if score > best[2]:
                        best = (i, j, score)
            i, j = best[0], best[1]
        else:
            i, j = 0, 1  # primi due (policy richiesta)

        z1 = marker_poses[i].R[:,2]
        z2 = marker_poses[j].R[:,2]
        Zc = -z1
        Zc /= (np.linalg.norm(Zc) + 1e-12)

        v = -z2
        Xc = v - np.dot(v, Zc) * Zc
        if np.linalg.norm(Xc) < 1e-6:
            # fallback: usa X del primo marker proiettata
            x_ref = marker_poses[i].R[:,0]
            Xc = x_ref - np.dot(x_ref, Zc) * Zc

        Xc /= (np.linalg.norm(Xc) + 1e-12)
        Yc = np.cross(Zc, Xc)
        Yc /= (np.linalg.norm(Yc) + 1e-12)

        R_cube = np.column_stack([Xc, Yc, Zc])

    else:
        # 1 solo marker
        R_ref = marker_poses[0].R
        Zc = -R_ref[:,2]
        Zc /= (np.linalg.norm(Zc) + 1e-12)

        x_ref = R_ref[:,0]
        Xc = x_ref - np.dot(x_ref, Zc) * Zc
        if np.linalg.norm(Xc) < 1e-6:
            y_ref = R_ref[:,1]
            Xc = y_ref - np.dot(y_ref, Zc) * Zc

        Xc /= (np.linalg.norm(Xc) + 1e-12)
        Yc = np.cross(Zc, Xc)
        Yc /= (np.linalg.norm(Yc) + 1e-12)

        R_cube = np.column_stack([Xc, Yc, Zc])

    rvec_cube, _ = cv.Rodrigues(R_cube)
    quat = _quat_from_R(R_cube)
    return CubePose(R_cube, t_cube, rvec_cube, quat)
