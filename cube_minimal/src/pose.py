import numpy as np
import cv2

def estimate_pose_ransac(obj_pts, img_pts, K, dist, ransac_err_px=3.0):
    """Tenta RANSAC (EPNP). Se fallisce, fallback a EPNP plain,
    e se hai solo 4 punti (una faccia), prova IPPE_SQUARE.
    Ritorna (rvec, tvec, inliers_or_None).
    """
    # 1) RANSAC EPNP con soglia più larga
    ok, rvec, tvec, inliers = cv2.solvePnPRansac(
        objectPoints=obj_pts, imagePoints=img_pts,
        cameraMatrix=K, distCoeffs=dist,
        flags=cv2.SOLVEPNP_EPNP,
        iterationsCount=300, reprojectionError=ransac_err_px, confidence=0.999
    )
    if ok and inliers is not None and len(inliers) >= 8:
        return rvec, tvec, inliers

    # 2) Fallback: EPNP plain su tutti i punti
    ok2, rvec2, tvec2 = cv2.solvePnP(obj_pts, img_pts, K, dist, flags=cv2.SOLVEPNP_EPNP)
    if ok2:
        return rvec2, tvec2, None

    # 3) Se sei con UNA sola faccia (4 punti), prova IPPE_SQUARE
    if obj_pts.shape[0] == 4:
        ok3, rvec3, tvec3 = cv2.solvePnP(obj_pts, img_pts, K, dist, flags=cv2.SOLVEPNP_IPPE_SQUARE)
        if ok3:
            return rvec3, tvec3, None

    # 4) Ultimo tentativo: AP3P (richiede >= 4 punti non complanari, ma a volte aiuta)
    ok4, rvec4, tvec4 = cv2.solvePnP(obj_pts, img_pts, K, dist, flags=cv2.SOLVEPNP_AP3P)
    if ok4:
        return rvec4, tvec4, None

    raise RuntimeError("PnP failed (RANSAC + fallbacks)")

def gather_obj_img_points(detection, id_to_obj):
    if detection.ids is None:
        return None, None
    obj, img = [], []
    for i, mid in enumerate(detection.ids.ravel().tolist()):
        if mid not in id_to_obj:
            continue
        obj.append(id_to_obj[mid])            # (4,3)
        img.append(detection.corners[i].reshape(4,2))  # (4,2)
    if not obj:
        return None, None
    return (np.vstack(obj).astype(np.float32),
            np.vstack(img).astype(np.float32))

def estimate_pose_epnp(obj_pts, img_pts, K, dist):

    # Algoritmo minimo: un'unica chiamata a solvePnP con EPNP
    ok, rvec, tvec = cv2.solvePnP(obj_pts, img_pts, K, dist, flags=cv2.SOLVEPNP_EPNP)
    if not ok:
        raise RuntimeError('solvePnP failed')
    return rvec, tvec

def refit_front_faces(detection, id_to_obj, K, dist, rvec, tvec):
    R, _ = cv2.Rodrigues(rvec)
    obj_keep, img_keep = [], []
    if detection.ids is None:
        return rvec, tvec
    for i, mid in enumerate(detection.ids.ravel().tolist()):
        if mid not in id_to_obj: 
            continue
        pts = id_to_obj[mid].astype(np.float32)
        n_obj = np.cross(pts[1]-pts[0], pts[2]-pts[1]); n = n_obj / (np.linalg.norm(n_obj)+1e-9)
        n_cam = (R @ n.reshape(3,1)).ravel()
        if n_cam[2] < 0:  # normale verso camera
            obj_keep.append(pts)
            img_keep.append(detection.corners[i].reshape(4,2).astype(np.float32))
    if not obj_keep:
        return rvec, tvec
    obj = np.vstack(obj_keep); img = np.vstack(img_keep)
    ok, r2, t2 = cv2.solvePnP(obj, img, K, dist, flags=cv2.SOLVEPNP_EPNP)
    return (r2, t2) if ok else (rvec, tvec)

def estimate_center_from_single_markers(detection, K, dist, marker_mm, cube_edge_mm,
                                        angle_weight=True, huber_delta_mm=50.0):
    """
    Stima il centro del cubo usando SOLO pose per-marker (IPPE/EPNP), poi media robusta.
    Ritorna (O_mm, num_used, per_id_dbg) dove O_mm è (3,) in mm.
    """
    if detection.ids is None or len(detection.ids) == 0:
        return None, 0, {}

    # punti 3D nel frame del marker (z=0), ordine ArUco TL,TR,BR,BL
    h = float(marker_mm) / 2.0
    obj4 = np.array([[-h,  h, 0.0],
                     [ h,  h, 0.0],
                     [ h, -h, 0.0],
                     [-h, -h, 0.0]], dtype=np.float32)

    O_candidates = []
    dbg = {}  # id -> info (angolo, err px)

    for i, mid in enumerate(detection.ids.ravel().tolist()):
        img4 = detection.corners[i].reshape(4,2).astype(np.float32)

        # 1) Pose per-marker (IPPE più stabile sui quadrati planari)
        ok, rvec, tvec = cv2.solvePnP(obj4, img4, K, dist, flags=cv2.SOLVEPNP_IPPE_SQUARE)
        if not ok:
            ok, rvec, tvec = cv2.solvePnP(obj4, img4, K, dist, flags=cv2.SOLVEPNP_EPNP)
            if not ok: 
                continue

        R, _ = cv2.Rodrigues(rvec)
        n_cam = (R @ np.array([0,0,1.0]).reshape(3,1)).ravel()  # normale della faccia in camera
        n_cam = n_cam / (np.linalg.norm(n_cam) + 1e-9)

        # 2) Centro proposto da questo marker
        O_i = tvec.ravel() - (cube_edge_mm * 0.5) * n_cam

        # qualità: preferisci facce più frontali (peso ~ cos(theta))
        w = abs(n_cam[2]) if angle_weight else 1.0

        # errore medio di riproiezione (debug)
        proj, _ = cv2.projectPoints(obj4, rvec, tvec, K, dist)
        e = np.linalg.norm(proj.reshape(-1,2) - img4, axis=1).mean()

        O_candidates.append((O_i, w))
        dbg[int(mid)] = {'cos_theta': float(abs(n_cam[2])), 'reproj_px': float(e)}

    if not O_candidates:
        return None, 0, dbg

    # 3) Media robusta (Huber): inizializza con media pesata da cos(theta)
    O0 = np.average(np.array([O for O,_ in O_candidates]), axis=0,
                    weights=np.array([w for _,w in O_candidates]))
    O = O0.copy()

    for _ in range(5):  # poche iterazioni
        resid = []
        weights = []
        for Oi, w in O_candidates:
            r = np.linalg.norm(Oi - O)
            # peso Huber in mm
            if r <= huber_delta_mm:
                alpha = 1.0
            else:
                alpha = huber_delta_mm / (r + 1e-9)
            resid.append(Oi)
            weights.append(w * alpha)
        O = np.average(np.array(resid), axis=0, weights=np.array(weights))

    return O, len(O_candidates), dbg
