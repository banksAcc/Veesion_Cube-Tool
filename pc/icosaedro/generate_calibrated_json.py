import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from scipy.spatial import ConvexHull
import cv2 as cv
import json

# ==========================================
# 1. CONFIGURAZIONE UTENTE
# ==========================================

# Tipo di ArUco
ARUCO_DICT = cv.aruco.DICT_4X4_50 

# MAPPING: Faccia -> ID ArUco
FACE_TO_ID = {
    # --- Pentagoni (P) ---
    "P0": 3,   "P1": 11,  "P2": 7,   "P3": 22,  "P4": 16,  "P5": 25,
    "P6": 14,  "P7": 13,  "P8": 8,   "P10": 26, "P11": 24,
    # P9 (Base)

    # --- Esagoni (H) ---
    "H0": 5,   "H1": 17,  "H2": 2,   "H3": 4,   "H4": 9,  "H5": 1,
    "H6": 6,   "H7": 18,  "H8": 10,   "H9": 12,  "H10": 27, "H11": 29,
    "H12": 31, "H13": 23, "H14": 19, "H15": 15, "H16": 28, "H17": 20,
    "H18": 30, "H19": 21
}

# OFFSET MANUALI (Gradi Antiorari)
# Esempio: "P0": 90 ruota il marker P0 di 90 gradi a sinistra.
MANUAL_OFFSETS = {
    "H11": 120,
    "H12": -60,
    "H18": -30,
    "H16": -60,
    "H10": -150,
    "P5": -54,
    "H13": 90,
    "P11": 234,
    "H14": 120,
    "H19": 60,
    "H1": 180,
    "H7": -60,
    "P7": -54,
    "H9": -120,
    "P3": -54,
    "H17": 180,
    "P10": -126,
    "H8": -60,
    "P1": -18,
    "P2": 180,
    "H4": -90,
    "P8": -180,
    "H6": -150,
    "H5": 120,
    "H15": -120,
    "P4": 90,
    "H0": 90,
    "H3": 120,
    "H2": 210,
    "P0": 180,
}

EDGE_LENGTH_METERS = 0.025
FILENAME = "transforms_final.json"

# ==========================================
# 2. HELPER GENERAZIONE ARUCO
# ==========================================
def get_aruco_bits(marker_id, dictionary_id=ARUCO_DICT):
    aruco_dict = cv.aruco.getPredefinedDictionary(dictionary_id)
    marker_bits = 4 + 2 
    img = cv.aruco.generateImageMarker(aruco_dict, marker_id, marker_bits)
    return (img > 128).astype(int)

# ==========================================
# 3. GEOMETRIA E PLOT
# ==========================================
def rotation_matrix_z(deg):
    rad = np.radians(deg)
    c, s = np.cos(rad), np.sin(rad)
    return np.array([[c, -s, 0, 0], [s,  c, 0, 0], [0,  0, 1, 0], [0,  0, 0, 1]])

def rotation_matrix_from_vectors(vec1, vec2):
    a, b = (vec1 / np.linalg.norm(vec1)).reshape(3), (vec2 / np.linalg.norm(vec2)).reshape(3)
    v = np.cross(a, b)
    c = np.dot(a, b)
    s = np.linalg.norm(v)
    if s == 0: return np.eye(3)
    kmat = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + kmat + kmat.dot(kmat) * ((1 - c) / (s ** 2))

def build_geometry_and_plot():
    # --- Costruzione Icosaedro ---
    phi = (1 + np.sqrt(5)) / 2
    verts = []
    for x in [0]:
        for y in [-1, 1]:
            for z in [-phi, phi]:
                verts.append([x, y, z]); verts.append([z, x, y]); verts.append([y, z, x])
    verts = np.array(verts)
    hull = ConvexHull(verts)
    
    new_faces = []; types = []
    # Esagoni
    for f in hull.simplices:
        A, B, C = verts[f[0]], verts[f[1]], verts[f[2]]
        new_faces.append([A+(B-A)/3, A+2*(B-A)/3, B+(C-B)/3, B+2*(C-B)/3, C+(A-C)/3, C+2*(A-C)/3])
        types.append('hex')
    # Pentagoni
    from scipy.spatial.distance import cdist
    dmat = cdist(verts, verts); min_d = np.min(dmat[dmat > 0.1])
    for i, v in enumerate(verts):
        neighs = np.where(np.isclose(dmat[i], min_d, atol=0.1))[0]
        pts = np.array([v + (verts[n]-v)/3.0 for n in neighs])
        n = v/np.linalg.norm(v)
        arb = np.array([0,0,1]) if abs(n[2])<0.9 else np.array([0,1,0])
        t1 = np.cross(n, arb); t1/=np.linalg.norm(t1); t2 = np.cross(n, t1)
        ang = np.arctan2(np.dot(pts-v, t2), np.dot(pts-v, t1))
        new_faces.append(pts[np.argsort(ang)])
        types.append('pent')

    all_c = np.vstack(new_faces)
    u_verts, u_inv = np.unique(np.round(all_c, 8), axis=0, return_inverse=True)
    face_indices = []
    c=0
    for f in new_faces: face_indices.append(u_inv[c:c+len(f)]); c+=len(f)
    
    pent_indices = [face_indices[i] for i, t in enumerate(types) if t == 'pent']
    hex_indices  = [face_indices[i] for i, t in enumerate(types) if t == 'hex']

    # Rotazione Globale
    p0_center = np.mean(u_verts[pent_indices[0]], axis=0)
    R_align = rotation_matrix_from_vectors(p0_center, np.array([0,0,1]))
    u_verts = (R_align @ u_verts.T).T
    
    scale = EDGE_LENGTH_METERS / np.linalg.norm(u_verts[pent_indices[0][0]] - u_verts[pent_indices[0][1]])
    u_verts *= scale

    # --- VISUALIZZAZIONE ---
    fig = plt.figure(figsize=(12, 12))
    ax = fig.add_subplot(111, projection="3d")
    
    transforms = {}

    def process_and_draw(indices, prefix):
        for i, idxs in enumerate(indices):
            coords = u_verts[idxs]
            center = np.mean(coords, axis=0)
            
            # 1. Calcolo Frame Standard
            z_axis = center / np.linalg.norm(center)
            vec_v0 = coords[0] - center 
            x_temp = vec_v0 / np.linalg.norm(vec_v0)
            y_axis = np.cross(z_axis, x_temp); y_axis/=np.linalg.norm(y_axis)
            x_axis = np.cross(y_axis, z_axis); x_axis/=np.linalg.norm(x_axis)
            
            # Offset Manuale
            name = f"{prefix}{i}"
            offset = MANUAL_OFFSETS.get(name, 0)
            R_off = rotation_matrix_z(offset)
            
            # Matrice Finale (Ruota gli assi X,Y sulla faccia)
            T_std = np.eye(4)
            T_std[:3,0]=x_axis; T_std[:3,1]=y_axis; T_std[:3,2]=z_axis; T_std[:3,3]=center
            T_final = T_std @ R_off
            
            transforms[name] = np.linalg.inv(T_final).tolist()
            
            # Colore Faccia
            face_color = '#aaaaaa' 
            face_alpha = 0.4
            if name == "P9":
                face_color = '#ff0000' # Rosso per la base
                face_alpha = 0.6       
            
            poly = Poly3DCollection([coords], alpha=face_alpha, facecolor=face_color, edgecolor='#666666')
            ax.add_collection3d(poly)
            
            # Disegno Marker
            marker_id = FACE_TO_ID.get(name)
            
            if marker_id is not None:
                bits = get_aruco_bits(marker_id)
                
                # RIMOSSO: bits = np.rot90(bits, ...)
                # La rotazione ora è gestita interamente da T_final (X_F, Y_F)
                
                N = bits.shape[0]
                marker_size = EDGE_LENGTH_METERS * 0.85
                step = marker_size / N
                start_x = -marker_size / 2
                start_y = marker_size / 2
                
                # Lift 2mm
                epsilon = 0.002 * z_axis 
                
                # Nuovi assi ruotati
                X_F = T_final[:3, 0]
                Y_F = T_final[:3, 1]
                
                pixel_polys = []
                pixel_colors = []
                
                for r in range(N):
                    for c in range(N):
                        color = 'white' if bits[r, c] == 1 else 'black'
                        pl_x = start_x + c * step
                        pl_y = start_y - r * step 
                        
                        p0 = center + (pl_x)*X_F + (pl_y)*Y_F + epsilon
                        p1 = center + (pl_x+step)*X_F + (pl_y)*Y_F + epsilon
                        p2 = center + (pl_x+step)*X_F + (pl_y-step)*Y_F + epsilon
                        p3 = center + (pl_x)*X_F + (pl_y-step)*Y_F + epsilon
                        
                        pixel_polys.append([p0, p1, p2, p3])
                        pixel_colors.append(color)
                
                coll = Poly3DCollection(pixel_polys, facecolors=pixel_colors, edgecolors=None) 
                ax.add_collection3d(coll)

                # ID in BLU
                txt_pos = center + z_axis * (EDGE_LENGTH_METERS * 1.0)
                ax.text(txt_pos[0], txt_pos[1], txt_pos[2], f"{marker_id}", 
                        ha='center', va='center', fontsize=9, color='blue', weight='bold') # <-- COLORE CAMBIATO

            else:
                txt_pos = center + z_axis * 0.005
                label_txt = name if name != "P9" else "P9 (BASE)"
                col_txt = 'blue' if name != "P9" else 'black'
                ax.text(txt_pos[0], txt_pos[1], txt_pos[2], label_txt, ha='center', fontsize=8, color=col_txt, weight='bold')

    process_and_draw(pent_indices, "P")
    process_and_draw(hex_indices,  "H")
    
    lim = 0.07
    ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim); ax.set_zlim(-lim, lim)
    ax.set_box_aspect([1,1,1])
    ax.axis('off')
    
    ax.view_init(elev=30, azim=45)
    
    plt.tight_layout()
    plt.show()
    
    with open(FILENAME, "w") as f:
        json.dump(transforms, f, indent=4)
    print(f"JSON salvato in {FILENAME}")

if __name__ == "__main__":
    build_geometry_and_plot()