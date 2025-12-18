import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from scipy.spatial import ConvexHull
import json

# ==========================================
# CONFIGURAZIONE
# ==========================================
EDGE_LENGTH_METERS = 0.025  # 25mm = 0.025 metri
FILENAME = "transforms_face_to_body_v2.json"

# Dizionario degli offset angolari (rotazione attorno a Z locale della faccia)
# Se un ID non è in lista, l'offset sarà 0.
MANUAL_OFFSETS = {
    "H11": 120, "H12": -60, "H18": -30, "H16": -60, "H10": -150,
    "P5": -54,  "H13": 90,  "P11": 234, "H14": 120, "H19": 60,
    "H1": 180,  "H7": -60,  "P7": -54,  "H9": -120, "P3": -54,
    "H17": 180, "P10": -126,"H8": -60,  "P1": -18,  "P2": 180,
    "H4": -90,  "P8": -180, "H6": -150, "H5": 120,  "H15": -120,
    "P4": 90,   "H0": 90,   "H3": 120,  "H2": 210,  "P0": 36,
}

def rotation_matrix_from_vectors(vec1, vec2):
    """Allinea vec1 a vec2."""
    a, b = (vec1 / np.linalg.norm(vec1)).reshape(3), (vec2 / np.linalg.norm(vec2)).reshape(3)
    v = np.cross(a, b)
    c = np.dot(a, b)
    s = np.linalg.norm(v)
    if s == 0: return np.eye(3)
    kmat = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + kmat + kmat.dot(kmat) * ((1 - c) / (s ** 2))

def get_z_rotation_matrix(degrees):
    """Restituisce una matrice 4x4 di rotazione attorno a Z."""
    rad = np.radians(degrees)
    c, s = np.cos(rad), np.sin(rad)
    return np.array([
        [c, -s, 0, 0],
        [s,  c, 0, 0],
        [0,  0, 1, 0],
        [0,  0, 0, 1]
    ])

def build_geometry_and_save():
    # 1. Icosaedro Base
    phi = (1 + np.sqrt(5)) / 2
    verts = []
    for x in [0]:
        for y in [-1, 1]:
            for z in [-phi, phi]:
                verts.append([x, y, z]); verts.append([z, x, y]); verts.append([y, z, x])
    verts = np.array(verts)
    
    # 2. Generazione Facce (Troncatura)
    hull = ConvexHull(verts)
    new_faces = []
    types = [] # 'hex', 'pent'
    
    # Esagoni (dalle facce)
    for f in hull.simplices:
        pts = verts[f]
        A, B, C = pts[0], pts[1], pts[2]
        new_faces.append([
            A+(B-A)/3, A+2*(B-A)/3, B+(C-B)/3, B+2*(C-B)/3, C+(A-C)/3, C+2*(A-C)/3
        ])
        types.append('hex')
        
    # Pentagoni (dai vertici)
    from scipy.spatial.distance import cdist
    dmat = cdist(verts, verts)
    min_d = np.min(dmat[dmat > 0.1])
    for i, v in enumerate(verts):
        neighs = np.where(np.isclose(dmat[i], min_d, atol=0.1))[0]
        pts = [v + (verts[n]-v)/3.0 for n in neighs]
        # Ordina
        pts = np.array(pts)
        n = v/np.linalg.norm(v)
        arb = np.array([0,0,1]) if abs(n[2])<0.9 else np.array([0,1,0])
        t1 = np.cross(n, arb); t1/=np.linalg.norm(t1)
        t2 = np.cross(n, t1)
        ang = np.arctan2(np.dot(pts-v, t2), np.dot(pts-v, t1))
        new_faces.append(pts[np.argsort(ang)])
        types.append('pent')

    # Unifica
    all_c = np.vstack(new_faces)
    u_verts, u_inv = np.unique(np.round(all_c, 8), axis=0, return_inverse=True)
    
    faces_idx = []
    c=0
    for f in new_faces:
        faces_idx.append(u_inv[c:c+len(f)])
        c+=len(f)
        
    pent_indices = [faces_idx[i] for i, t in enumerate(types) if t == 'pent']
    hex_indices  = [faces_idx[i] for i, t in enumerate(types) if t == 'hex']

    # 3. ROTAZIONE DI ALLINEAMENTO (Z_BODY su P0)
    p0_center = np.mean(u_verts[pent_indices[0]], axis=0)
    target_z = np.array([0.0, 0.0, 1.0]) 
    R_align = rotation_matrix_from_vectors(p0_center, target_z)
    u_verts = (R_align @ u_verts.T).T

    # 4. SCALATURA IN METRI
    curr_edge = np.linalg.norm(u_verts[pent_indices[0][0]] - u_verts[pent_indices[0][1]])
    scale = EDGE_LENGTH_METERS / curr_edge
    u_verts *= scale

    # 5. CALCOLO MATRICI CON OFFSET
    transforms = {}
    
    def process_faces(indices, prefix):
        for i, idxs in enumerate(indices):
            face_name = f"{prefix}{i}"
            coords = u_verts[idxs]
            center = np.mean(coords, axis=0)
            
            # --- Frame Geometrico Standard ---
            # Z=Normale, X=Verso primo vertice
            z_axis = center / np.linalg.norm(center)
            x_temp = coords[0] - center
            x_temp /= np.linalg.norm(x_temp)
            y_axis = np.cross(z_axis, x_temp); y_axis/=np.linalg.norm(y_axis)
            x_axis = np.cross(y_axis, z_axis); x_axis/=np.linalg.norm(x_axis)
            
            # Matrice Body -> Face (Geometrica)
            T_body_face_geom = np.eye(4)
            T_body_face_geom[:3, 0] = x_axis
            T_body_face_geom[:3, 1] = y_axis
            T_body_face_geom[:3, 2] = z_axis
            T_body_face_geom[:3, 3] = center
            
            # --- Applicazione Offset Manuale ---
            # Recuperiamo l'angolo dal dizionario (0 se non esiste)
            offset_angle = MANUAL_OFFSETS.get(face_name, 0.0)
            
            # Creiamo matrice di rotazione Z locale
            R_offset = get_z_rotation_matrix(offset_angle)
            
            # La posa del MARKER reale è la posa geometrica ruotata localmente
            T_body_face_marker = T_body_face_geom @ R_offset
            
            # Quello che ci serve nel JSON: Marker -> Body
            # (Ovvero l'inversa della posa del marker rispetto al body)
            T_face_body = np.linalg.inv(T_body_face_marker)
            transforms[face_name] = T_face_body.tolist()
            
            # Debug per P0 per confermare che l'offset venga preso
            if face_name == "P0":
                print(f"P0 Offset applicato: {offset_angle} gradi")

    process_faces(pent_indices, "P")
    process_faces(hex_indices,  "H")
    
    with open(FILENAME, "w") as f:
        json.dump(transforms, f, indent=4)
    print(f"Salvato {FILENAME} con {len(transforms)} trasformazioni.")
    print("Nota: Le rotazioni manuali sono state incorporate.")

    # Controllo ID mancanti
    all_keys = set(transforms.keys())
    offset_keys = set(MANUAL_OFFSETS.keys())
    missing_in_offsets = all_keys - offset_keys
    if missing_in_offsets:
        print(f"ATTENZIONE: Nessun offset trovato per: {sorted(list(missing_in_offsets))}")
        print("Verrà usato offset 0.0 per questi.")

if __name__ == "__main__":
    build_geometry_and_save()