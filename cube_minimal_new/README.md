# Cube Minimal ArUco Pose — **README**

Sistema **ultra‑semplice** per stimare la **posa del centro** di un **cubo** con **6 marker ArUco** (DICT_4X4_100), senza preprocess, senza refine: **solo** rilevamento marker → PnP (**EPNP**). Pensato per **test da banco su immagini**.

---

## 🔧 Requisiti

- Python 3.9+
- OpenCV (contrib) + NumPy + PyYAML

```bash
pip install opencv-contrib-python numpy pyyaml
```

---

## 📁 Struttura progetto

```
cube_minimal/
  README.md
  config/
    camera.yaml            # intrinseci + distorsione (OpenCV format) — oppure
    camera.npz             # alternativa NumPy (.npz) con K e dist
  src/
    __init__.py
    camera_io.py           # loader YAML/NPZ -> (K, dist)
    cube_model.py          # geometria del cubo -> punti 3D (corner di ogni marker)
    detect.py              # rilevamento ArUco (DICT_4X4_100)
    pose.py                # PnP minimale (solvePnP EPNP)
    run_image.py           # stima posa su singola immagine (+ overlay opzionale)
    eval_folder.py         # stima jitter su cartella di immagini
```

> **Nota**: se non hai `camera_io.py` e il codice carica solo YAML, usa direttamente `camera.yaml`. Questo README supporta **entrambe** le modalità.

---

## 🎯 Specifiche geometriche

- **Cubo**: lato **60 mm**, origine del frame oggetto **al centro** del cubo.
- **Marker**: lato **55 mm**, **centrati** su ciascuna delle 6 facce.
- **Dizionario**: `DICT_4X4_100` (ID consigliati: `0..5`).  
- **Mappatura ID ↔ facce (default)**:  
  `+X:0, -X:1, +Y:2, -Y:3, +Z:4, -Z:5` (modificabile in `cube_model.py`).

**Output**: `rvec, tvec` della posa dell’oggetto nel frame camera; **`tvec` (mm)** è la **posizione del centro del cubo**.

---

## 📷 Calibrazione camera (file accettati)

### Opzione A — YAML stile OpenCV
```yaml
%YAML:1.0
camera_matrix:
  rows: 3
  cols: 3
  dt: d
  data: [fx, 0.0, cx,
         0.0, fy, cy,
         0.0, 0.0, 1.0]

# 5, 8, 12 o 14 coeff. nel classico ordine OpenCV:
# [k1, k2, p1, p2, k3, k4, k5, k6, s1, s2, s3, s4, tau_x, tau_y]
distortion_coefficients:
  rows: 1
  cols: 8
  dt: d
  data: [k1, k2, p1, p2, k3, k4, k5, k6]
```

### Opzione B — NPZ (NumPy)
Salva con:
```python
import numpy as np
np.savez('config/camera.npz', cameraMatrix=K, distCoeffs=dist)
```
Il loader accetta anche chiavi alternative: `K`/`mtx` e `dist`/`D`.

---

## ▶️ Esecuzione su una singola immagine

```bash
python -m src.run_image \
  --image data/test.jpg \
  --camera config/camera.yaml \
  --edge_mm 60 --marker_mm 55
```

**Overlay di visualizzazione (se supportato nel tuo `run_image.py`):**
```bash
python -m src.run_image \
  --image data/test.jpg \
  --camera config/camera.yaml \
  --edge_mm 60 --marker_mm 55 \
  --viz --out out/overlay.jpg --show
```
L’overlay disegna:
- contorni + ID dei marker rilevati,
- assi del frame oggetto (al centro del cubo),
- wireframe del cubo,
- proiezione dei 4 corner 3D di ogni marker impiegato nel PnP.

---

## 📊 Valutazione jitter su cartella

```bash
python -m src.eval_folder \
  --images_dir data/static_seq \
  --camera config/camera.npz \
  --edge_mm 60 --marker_mm 55
```
Stampa media e deviazione standard (mm) di `tvec` sugli assi, e il numero di frame validi.

---

## 🧠 Come funziona (in breve)

1. **Detect**: rileva i marker ArUco (`DICT_4X4_100`) e affina i corner con **cornerSubPix** (opzionale ma consigliato).  
2. **Cubo → 3D**: `cube_model.py` genera per ogni faccia (ID) i **4 corner 3D** nel frame oggetto (centro cubo).  
3. **PnP (EPNP)**: `solvePnP` con **tutti i corner visibili** → ottieni `rvec, tvec`. **Nessun** RANSAC/LM/refine per massima semplicità.  
4. **Centro cubo**: `tvec` è direttamente il **centro** del cubo in coordinate camera (unità = **mm**).

---

## 🧩 Personalizzazioni rapide

- **ID diversi o facce scambiate?** Aggiorna la mappa in `cube_model.py` (`id_order`).  
- **Cubi/marker di dimensioni differenti?** Passa `--edge_mm` e `--marker_mm` agli script.  
- **Solo YAML?** Usa `config/camera.yaml` e il loader base.  
- **Solo NPZ?** Usa `config/camera.npz` con il loader unificato (`camera_io.py`).

---

## ❗ Troubleshooting

- **Instabilità con una sola faccia**: mostra almeno **2 facce** (8+ punti totali) per stabilizzare EPNP.  
- **Unità errate (t troppo grande/piccolo)**: controlla **scala marker** (55 mm reali) e **focali in pixel**.  
- **Distorsione anomala**: verifica che i coefficienti (`k1..k6`, ecc.) corrispondano al **modello OpenCV** usato in calibrazione.  
- **ID non riconosciuti**: assicurati che i tag appartengano a `DICT_4X4_100` e che gli **ID** corrispondano alla mappa facce.

---

## 📝 API e file chiave (panoramica)

- `camera_io.py` → `load_camera_any(path) -> (K, dist)` (YAML/NPZ).  
- `cube_model.py` → `build_cube_id_to_obj(edge_mm, marker_mm, id_order)` → dict `id -> (4x3)` corner 3D.  
- `detect.py` → `detect_markers(gray)` → corner 2D + ID.  
- `pose.py` → `gather_obj_img_points(...)` e `estimate_pose_epnp(...)`.  
- `run_image.py` → dimostratore per una singola immagine (con overlay opzionale).  
- `eval_folder.py` → valutazione statistica su una sequenza di immagini.

---

## 🧪 Esempio di YAML completo

```yaml
%YAML:1.0
camera_matrix:
  rows: 3
  cols: 3
  dt: d
  data: [3698.038239605276, 0.0, 999.3938934566954,
         0.0, 3695.761718639665, 740.5822907590251,
         0.0, 0.0, 1.0]
distortion_coefficients:
  rows: 1
  cols: 8
  dt: d
  data: [34.30335190665902, -14.683394753342217,
         0.00016366960704890915, 0.0005592836138473655,
         6.3960875378705095, 34.41411329223707,
         -11.977003422186023, -3.8757456337347103]
```

> Se i tuoi coefficienti sono 5, usa `cols: 5` e togli i k4..k6. Se usi NPZ, non serve questo YAML.

---

## ✅ Checklist rapido

- [ ] `config/camera.yaml` **o** `config/camera.npz` presente e corretto.  
- [ ] Cubo con **6 tag** 55 mm centrati; **dizionario** `DICT_4X4_100`.  
- [ ] Almeno **2 facce** visibili nell’immagine.  
- [ ] Eseguito `run_image.py` e verificato `tvec` (mm).  
- [ ] (Opz.) `eval_folder.py` per jitter/stabilità.