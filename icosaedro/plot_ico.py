import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from scipy.spatial import ConvexHull
import json

# --- 1. COSTRUZIONE GEOMETRIA (Standard) ---
def build_truncated_icosahedron(edge_length_mm: float):
    phi = (1 + np.sqrt(5)) / 2
    verts_ico = []
    for x in [0]:
        for y in [-1, 1]:
            for z in [-phi, phi]:
                verts_ico.append([x, y, z])
                verts_ico.append([z, x, y])
                verts_ico.append([y, z, x])
    verts_ico = np.array(verts_ico)
    
    hull = ConvexHull(verts_ico)
    ico_faces = hull.simplices
    
    new_faces_coords = []
    types = [] 
    
    # Esagoni
    for face in ico_faces:
        A, B, C = verts_ico[face[0]], verts_ico[face[1]], verts_ico[face[2]]
        hex_face = [
            A + (B - A)/3.0, A + 2*(B - A)/3.0,
            B + (C - B)/3.0, B + 2*(C - B)/3.0,
            C + (A - C)/3.0, C + 2*(A - C)/3.0
        ]
        new_faces_coords.append(hex_face)
        types.append('hex')

    # Pentagoni
    from scipy.spatial.distance import cdist
    dist_matrix = cdist(verts_ico, verts_ico)
    min_dist = np.min(dist_matrix[dist_matrix > 0.1])
    
    for i, v in enumerate(verts_ico):
        neighbors = np.where(np.isclose(dist_matrix[i], min_dist, atol=0.1))[0]
        p_verts = [v + (verts_ico[n] - v)/3.0 for n in neighbors]
        
        # Ordinamento angolare
        p_verts = np.array(p_verts)
        norm = v / np.linalg.norm(v)
        arb = np.array([0,0,1]) if abs(norm[2]) < 0.9 else np.array([0,1,0])
        t1 = np.cross(norm, arb); t1/=np.linalg.norm(t1)
        t2 = np.cross(norm, t1)
        angles = np.arctan2(np.dot(p_verts-v, t2), np.dot(p_verts-v, t1))
        new_faces_coords.append(p_verts[np.argsort(angles)])
        types.append('pent')

    # Unifica e Scala
    all_c = np.vstack(new_faces_coords)
    u_verts, u_inv = np.unique(np.round(all_c, 6), axis=0, return_inverse=True)
    
    face_indices = []
    c = 0
    for f in new_faces_coords:
        face_indices.append(u_inv[c:c+len(f)])
        c += len(f)

    pent_faces = [face_indices[i] for i, t in enumerate(types) if t == 'pent']
    hex_faces = [face_indices[i] for i, t in enumerate(types) if t == 'hex']
    
    curr_edge = np.linalg.norm(u_verts[pent_faces[0][0]] - u_verts[pent_faces[0][1]])
    scale = edge_length_mm / curr_edge
    
    return {
        "vertices": u_verts * scale,
        "pent_faces": pent_faces,
        "hex_faces": hex_faces
    }

# --- 2. CALCOLO FRAME E MATRICE INVERSA ---
def compute_frame_matrix(center, first_vertex):
    """
    Restituisce T_body_to_face:
    Origine: Centro Faccia
    Z: Normale Uscente
    X: Verso il primo vertice
    """
    origin = center 
    z_axis = center / np.linalg.norm(center)
    vec_v = first_vertex - center
    x_temp = vec_v / np.linalg.norm(vec_v)
    y_axis = np.cross(z_axis, x_temp); y_axis /= np.linalg.norm(y_axis)
    x_axis = np.cross(y_axis, z_axis); x_axis /= np.linalg.norm(x_axis)
    
    T = np.eye(4)
    T[0:3, 0] = x_axis
    T[0:3, 1] = y_axis
    T[0:3, 2] = z_axis
    T[0:3, 3] = origin
    return T

def process_geometry_and_save(edge_len=25.0, filename="transforms_face_to_body.json"):
    geo = build_truncated_icosahedron(edge_len)
    V = geo["vertices"]
    
    # Dizionario per salvare le matrici T_Face_to_Body
    transforms_inverse = {}
    
    # Dati per il plot (usiamo ancora T_Body_to_Face per disegnare le terne SULLE facce)
    plot_data = {"centers":[], "x":[], "y":[], "z":[], "labels":[], "polys":[]}
    
    def add_face_data(face_indices, prefix, idx):
        coords = V[face_indices]
        center = np.mean(coords, axis=0)
        
        # 1. Calcoliamo la matrice diretta: Dal Centro Solido alla Faccia
        T_body_to_face = compute_frame_matrix(center, coords[0])
        
        # 2. Calcoliamo l'INVERSA: Dalla Faccia al Centro Solido
        # Questa è quella che serve a te per ritrovare il centro partendo dalla faccia
        T_face_to_body = np.linalg.inv(T_body_to_face)
        
        name = f"{prefix}{idx}"
        
        # Salviamo l'INVERSA nel JSON
        transforms_inverse[name] = T_face_to_body.tolist()
        
        # Salviamo la DIRETTA per il plot (perché vogliamo disegnare gli assi sulla faccia)
        plot_data["centers"].append(center)
        plot_data["x"].append(T_body_to_face[0:3,0])
        plot_data["y"].append(T_body_to_face[0:3,1])
        plot_data["z"].append(T_body_to_face[0:3,2])
        plot_data["labels"].append(name)
        plot_data["polys"].append(coords)

    # Elaborazione
    for i, f in enumerate(geo["pent_faces"]): add_face_data(f, "P", i)
    for i, f in enumerate(geo["hex_faces"]):  add_face_data(f, "H", i)
    
    # Salvataggio JSON
    with open(filename, "w") as f:
        json.dump(transforms_inverse, f, indent=4)
        
    print(f"Salvato '{filename}' con {len(transforms_inverse)} matrici (FACE -> BODY).")
    return plot_data

# --- 3. VISUALIZZAZIONE ---
def plot_final_setup(plot_data, body_radius_approx=60):
    fig = plt.figure(figsize=(12, 12))
    ax = fig.add_subplot(111, projection="3d")
    
    # Solido Opaco
    coll = Poly3DCollection(plot_data["polys"], alpha=0.6, facecolor='#eeeeee', edgecolor='#444444', linewidths=0.5)
    ax.add_collection3d(coll)
    
    # BODY FRAME (Gigante al centro)
    L_body = body_radius_approx * 1.6
    o = [0,0,0]
    ax.quiver(o[0], o[1], o[2], 1, 0, 0, length=L_body, color='#cc0000', linewidth=4, arrow_length_ratio=0.05)
    ax.quiver(o[0], o[1], o[2], 0, 1, 0, length=L_body, color='#00cc00', linewidth=4, arrow_length_ratio=0.05)
    ax.quiver(o[0], o[1], o[2], 0, 0, 1, length=L_body, color='#0000cc', linewidth=4, arrow_length_ratio=0.05)
    ax.text(L_body,0,0,"X_BODY", color='#cc0000', fontsize=12, weight='bold')
    
    # FACE FRAMES
    centers = np.array(plot_data["centers"])
    X, Y, Z = np.array(plot_data["x"]), np.array(plot_data["y"]), np.array(plot_data["z"])
    L_face = 10.0
    ax.quiver(centers[:,0], centers[:,1], centers[:,2], X[:,0], X[:,1], X[:,2], length=L_face, color='r', linewidth=1)
    ax.quiver(centers[:,0], centers[:,1], centers[:,2], Y[:,0], Y[:,1], Y[:,2], length=L_face, color='g', linewidth=1)
    ax.quiver(centers[:,0], centers[:,1], centers[:,2], Z[:,0], Z[:,1], Z[:,2], length=L_face, color='b', linewidth=1)

    # Etichette
    for i, txt in enumerate(plot_data["labels"]):
        pos = centers[i] + Z[i]*(L_face*1.5)
        ax.text(pos[0], pos[1], pos[2], txt, fontsize=8, ha='center', color='k')

    # Limiti
    all_pts = np.vstack(plot_data["polys"])
    lim = np.ptp(all_pts.flatten()) * 0.5
    ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim); ax.set_zlim(-lim, lim)
    ax.set_box_aspect([1,1,1])
    ax.axis('off')
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    # Eseguiamo
    data = process_geometry_and_save(edge_len=25.0)
    plot_final_setup(data, body_radius_approx=60)