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