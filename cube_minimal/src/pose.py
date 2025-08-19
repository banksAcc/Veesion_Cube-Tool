import numpy as np
import cv2


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