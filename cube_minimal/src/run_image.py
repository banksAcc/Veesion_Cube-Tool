import argparse
import cv2
import yaml
import numpy as np
from pathlib import Path

from .cube_model import build_cube_id_to_obj
from .detect import detect_markers
from .pose import gather_obj_img_points, estimate_pose_epnp


def load_camera(path):
    with open(path, 'r') as f:
        y = yaml.safe_load(f)
    K = np.array(y['camera_matrix']['data']).reshape(3, 3)
    dist = np.array(y['distortion_coefficients']['data']).ravel()
    return K, dist


def cube_vertices(edge_mm: float):
    """8 vertici del cubo centrato nell'origine (frame oggetto)."""
    L = float(edge_mm)
    h = L / 2.0
    # ordine: z- (0..3), z+ (4..7)
    V = np.array([
        [-h, -h, -h], [ h, -h, -h], [ h,  h, -h], [-h,  h, -h],
        [-h, -h,  h], [ h, -h,  h], [ h,  h,  h], [-h,  h,  h]
    ], dtype=np.float32)
    edges = [(0,1),(1,2),(2,3),(3,0),
             (4,5),(5,6),(6,7),(7,4),
             (0,4),(1,5),(2,6),(3,7)]
    return V, edges


def project_points(obj_pts, rvec, tvec, K, dist):
    obj_pts = np.asarray(obj_pts, dtype=np.float32).reshape(-1, 3)
    img_pts, _ = cv2.projectPoints(obj_pts, rvec, tvec, K, dist)
    return img_pts.reshape(-1, 2)


def draw_overlay(bgr, rvec, tvec, K, dist, id_to_obj, det, edge_mm):
    """Disegna marker, assi, wireframe cubo e corner proiettati."""
    out = bgr.copy()

    # 1) Marker rilevati (contorni + ID)
    if det.ids is not None and len(det.ids) > 0:
        cv2.aruco.drawDetectedMarkers(out, det.corners, det.ids)

    # 2) Assi del frame oggetto al centro del cubo
    #    usa lunghezza asse pari a ~1/2 lato cubo per visibilità
    axis_len = max(10.0, edge_mm * 0.5)  # mm
    try:
        cv2.drawFrameAxes(out, K, dist, rvec, tvec, axis_len)
    except Exception:
        pass

    # 3) Wireframe del cubo
    V, E = cube_vertices(edge_mm)
    V2d = project_points(V, rvec, tvec, K, dist).astype(int)
    for a, b in E:
        pa, pb = tuple(V2d[a]), tuple(V2d[b])
        cv2.line(out, pa, pb, (255, 0, 255), 2, cv2.LINE_AA)

    # 4) Corner proiettati dei marker usati in PnP (per controllo)
    if det.ids is not None:
        for i, mid in enumerate(det.ids.ravel().tolist()):
            if mid not in id_to_obj:
                continue
            obj4 = id_to_obj[mid]  # (4,3) nel frame oggetto
            img4 = project_points(obj4, rvec, tvec, K, dist).astype(int)
            # polilinea verde
            cv2.polylines(out, [img4.reshape(-1,1,2)], True, (0, 255, 0), 2, cv2.LINE_AA)
            # punti blu
            for p in img4:
                cv2.circle(out, tuple(p), 3, (255, 128, 0), -1, cv2.LINE_AA)

    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--image', required=True)
    ap.add_argument('--camera', default='config/camera.yaml')
    ap.add_argument('--edge_mm', type=float, default=60.0)
    ap.add_argument('--marker_mm', type=float, default=55.0)
    ap.add_argument('--viz', action='store_true', help='Produce overlay di visualizzazione')
    ap.add_argument('--out', type=str, default='', help='Percorso file output overlay (png/jpg)')
    ap.add_argument('--show', action='store_true', help='Mostra una finestra con il risultato')
    args = ap.parse_args()

    # Carica camera
    K, dist = load_camera(args.camera)

    # Geometria cubo -> punti 3D corner dei marker
    id_to_obj = build_cube_id_to_obj(edge_mm=args.edge_mm, marker_mm=args.marker_mm)

    # Leggi immagine
    gray = cv2.imread(args.image, cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise SystemExit(f"Immagine non trovata: {args.image}")
    det = detect_markers(gray)

    # Raccogli corrispondenze e stima posa
    obj, img = gather_obj_img_points(det, id_to_obj)
    if obj is None:
        raise SystemExit("Nessun marker valido trovato nell'immagine")
    rvec, tvec = estimate_pose_epnp(obj, img, K, dist)

    print('rvec:', rvec.ravel())
    print('tvec (mm):', tvec.ravel())  # Centro del cubo nel frame camera

    if args.viz:
        # Prepara BGR per disegno
        bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        overlay = draw_overlay(bgr, rvec, tvec, K, dist, id_to_obj, det, edge_mm=args.edge_mm)

        # Salva se richiesto
        if args.out:
            out_path = Path(args.out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(out_path), overlay)
            print(f"Overlay salvato in: {out_path}")

        # Mostra se richiesto
        if args.show:
            cv2.imshow("overlay", overlay)
            cv2.waitKey(0)
            cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
