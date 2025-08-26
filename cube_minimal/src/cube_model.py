import numpy as np

# Rotazioni elementari

def rot_x(theta):
    c, s = np.cos(theta), np.sin(theta)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], dtype=float)

def rot_y(theta):
    c, s = np.cos(theta), np.sin(theta)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], dtype=float)

def rot_z(theta):
    c, s = np.cos(theta), np.sin(theta)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=float)


def build_cube_id_to_obj(edge_mm=60.0, marker_mm=55.0, id_order=None):
    """Ritorna un dict: id -> (4x3) punti 3D dei corner nel frame oggetto (centro cubo).
    id_order di default:
      { '+X':0, '-X':1, '+Y':2, '-Y':3, '+Z':4, '-Z':5 }
    """
    if id_order is None:
        id_order = {"+X":2, "-X":0, "+Y":4, "-Y":3, "+Z":5, "-Z":1}

    L = float(edge_mm)
    s = float(marker_mm)
    h = s / 2.0

    # Corner nel frame del marker (piano z=0), ordine ArUco canonico TL, TR, BR, BL
    corners_m = np.array([[-h,  h, 0.0],
                          [ h,  h, 0.0],
                          [ h, -h, 0.0],
                          [-h, -h, 0.0]], dtype=np.float32)

    # Definiamo per ogni faccia: rotazione R (marker->oggetto) e traslazione t (centro faccia)
    faces = {
        "+Z": (np.eye(3),                 np.array([0.0, 0.0,  L/2])),   # fronte
        "-Z": (rot_y(np.pi),              np.array([0.0, 0.0, -L/2])),   # retro (180° attorno a Y)
        "+X": (rot_y(-np.pi/2),           np.array([ L/2, 0.0, 0.0])),   # destra
        "-X": (rot_y( np.pi/2),           np.array([-L/2, 0.0, 0.0])),   # sinistra
        "+Y": (rot_x( np.pi/2),           np.array([0.0,  L/2, 0.0])),   # alto
        "-Y": (rot_x(-np.pi/2),           np.array([0.0, -L/2, 0.0])),   # basso
    }

    id_to_obj = {}
    for face, mid in id_order.items():
        R, t = faces[face]
        pts = (R @ corners_m.T).T + t  # (4,3)
        id_to_obj[int(mid)] = pts.astype(np.float32)

    return id_to_obj