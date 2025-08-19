import argparse
from pathlib import Path
import numpy as np
import cv2
import yaml
from .cube_model import build_cube_id_to_obj
from .detect import detect_markers
from .pose import gather_obj_img_points, estimate_pose_epnp


def load_camera(path):
    with open(path, 'r') as f:
        y = yaml.safe_load(f)
    import numpy as np
    K = np.array(y['camera_matrix']['data']).reshape(3,3)
    dist = np.array(y['distortion_coefficients']['data']).ravel()
    return K, dist


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--images_dir', required=True)
    ap.add_argument('--camera', default='config/camera.yaml')
    ap.add_argument('--edge_mm', type=float, default=60.0)
    ap.add_argument('--marker_mm', type=float, default=55.0)
    args = ap.parse_args()

    K, dist = load_camera(args.camera)
    id_to_obj = build_cube_id_to_obj(edge_mm=args.edge_mm, marker_mm=args.marker_mm)

    ts = []
    paths = sorted(list(Path(args.images_dir).glob('*.jpg')) + list(Path(args.images_dir).glob('*.png')))
    for p in paths:
        gray = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
        det = detect_markers(gray)
        obj, img = gather_obj_img_points(det, id_to_obj)
        if obj is None:
            continue
        _, tvec = estimate_pose_epnp(obj, img, K, dist)
        ts.append(tvec.ravel())

    if not ts:
        print('Nessuna posa stimata.')
        return

    T = np.vstack(ts)
    mu = T.mean(axis=0)
    sd = T.std(axis=0)
    print({'mean_mm': mu.tolist(), 'std_mm': sd.tolist(), 'num_frames': len(ts)})


if __name__ == '__main__':
    main()