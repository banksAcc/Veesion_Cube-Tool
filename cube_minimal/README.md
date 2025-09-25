# cube_pose - Stima posa cubo da marker ArUco

Mini-moduli riutilizzabili per:
- rilevare marker ArUco,
- stimare la posa dei singoli marker (IPPE SQUARE),
- ricostruire la posa di un **cubo** (centro + orientazione) usando 1..3 marker visibili,
- disegnare overlay di diagnostica.

> **Convenzione**: la Z del **marker** (asse blu) esce dal piano del marker (verso la camera);
> la Z del **cubo** è definita uscente dal cubo e per costruzione corrisponde a `-Z_marker` di una delle facce.

## Installazione

Da una shell nella radice del progetto:

```bash
pip install -e .
```

Oppure, per un installazione standard senza modifica del codice:

```bash
pip install .
```

Entrambi i comandi leggono le dipendenze elencate in `pyproject.toml` (`opencv-python` e `numpy`).

### Note su OpenCV
- Servono i moduli extra (ArUco incluso), assicurati che `opencv-python` sia almeno la versione `>=4.7`; in alternativa installa `opencv-contrib-python`.
- Su Linux potrebbe essere necessario avere installate le librerie di sistema per il supporto a GUI/video, ad esempio `sudo apt install libgl1`.
- Su Windows e macOS i wheel ufficiali includono gia il supporto ArUco.

## API principale

```python
from cube_minimal.cube_pose.api import estimate_cube_from_image

res = estimate_cube_from_image(
    image_or_path="cube_minimal/data/sample_dataset/example_1.png",
    camera_npz="cube_minimal/config/calib_data.npz",
    aruco_dict="4X4_50",
    marker_size=0.055,  # metri (lato del quadrato nero!)
    cube_size=0.060,    # metri
    pair_strategy="first",    # oppure "max_angle"
    return_overlay=True
)

tvec = res["tvec"]   # (3,) centro cubo in camera (m)
rvec = res["rvec"]   # (3,1) Rodrigues del cubo
R    = res["R"]      # (3,3) matrice di rotazione
quat = res["quat"]   # (4,) w,x,y,z
img  = res["overlay"]
```

### Output in sintesi

| Chiave | Shape | Contenuto |
| ------ | ----- | --------- |
| `tvec` | `(3,)` | Centro del cubo espresso nel frame camera (metri). |
| `rvec` | `(3,1)` | Vettore di rotazione in forma di Rodrigues relativo al cubo. |
| `R` | `(3,3)` | Matrice di rotazione del cubo, colonne = assi del cubo nel frame camera. |
| `quat` | `(4,)` | Quaternione `(w, x, y, z)` del cubo rispetto alla camera. |
| `overlay` | `H x W x 3` | Immagine originale con overlay diagnostico (se richiesto). |

## Dataset di esempio
- Le immagini di test sono in `cube_minimal/data/sample_dataset`.
- Il README dedicato ai dati contiene dettagli su calibrazione e convenzioni: vedi [`cube_minimal/data/README.md`](data/README.md).
- Per provare velocemente l API, usa il file `cube_minimal/data/sample_dataset/example_1.png` insieme alla calibrazione `cube_minimal/config/calib_data.npz`.

## CLI

Esempi assumendo il repository clonato localmente.

### Linux/macOS
```bash
python -m cube_minimal.cli.estimate_one \
    --image cube_minimal/data/sample_dataset/example_1.png \
    --camera cube_minimal/config/calib_data.npz \
    --aruco_dict 4X4_50 \
    --marker_size 0.055 \
    --cube_size 0.060 \
    --pair_strategy first \
    --out cube_minimal/data/sample_dataset/overlay.png \
    --show
```

### Windows (PowerShell)
```powershell
python -m cube_minimal.cli.estimate_one `
    --image cube_minimal\data\sample_dataset\example_1.png `
    --camera cube_minimal\config\calib_data.npz `
    --aruco_dict 4X4_50 `
    --marker_size 0.055 `
    --cube_size 0.060 `
    --pair_strategy first `
    --out cube_minimal\data\sample_dataset\overlay.png `
    --show
```

### Parametri principali
- `aruco_dict`: stringa della famiglia di marker (es. `4X4_50`, `5X5_100`). Deve corrispondere ai marker nel dataset.
- `marker_size`: lato del quadrato nero del marker in metri. Influisce direttamente sulla scala della posa.
- `cube_size`: lato del cubo fisico in metri. Determina il posizionamento del centro rispetto ai marker.
- `pair_strategy`: regolazione della fusione tra facce (`first` = usa la prima coppia trovata, `max_angle` = privilegia la coppia con facce piu ortogonali).

## Strategia di stima (riassunto)

1. **Detection** ArUco -> corner 2D (ordine: top-left, top-right, bottom-right, bottom-left).
2. **Pose marker** con `SOLVEPNP_IPPE_SQUARE` (viene scelta la soluzione a errore minimo).
3. **Centro cubo** da singolo marker: `t_marker - Z_marker * L/2`.
4. **Centro cubo finale** = media dei centri (1..3 marker).
5. **Orientazione cubo**:
   - Con `>=2` marker: `Z_cubo = -Z_marker_1`, `X_cubo` allineato alla seconda faccia (proiettato sul piano ortogonale a `Z_cubo`), `Y_cubo = Z_cubo x X_cubo`.
   - Con `1` marker: `Z_cubo = -Z_marker`, `X/Y` ricavati dal piano della stessa faccia.
6. Output: `tvec`, `rvec` (Rodrigues), `R`, `quat`.

## Requisiti
- `opencv-python`
- `numpy`

## Note importanti
- `marker_size` deve essere il lato del quadrato nero (no bordo bianco).
- Il file `.npz` della camera deve contenere `K`/`cameraMatrix` e `dist`/`distCoeffs`.
- Se usi piu marker e vuoi piu robustezza, prova `pair_strategy="max_angle"`.

## Test

I test si trovano nella cartella `tests`. Dopo aver installato il progetto (e `pytest`), esegui:

```bash
pytest tests
```

Oppure:

```bash
python -m pytest tests
```

Assicurati che l ambiente includa eventuali asset necessari (dataset di sample e parametri camera).

## TODO (prossimi sviluppi)
- Test automatici piu estesi (copertura funzioni in `cube_pose`).
- Migliorare la stima del centro (mediana o pesi per facce di qualita diversa).
- Metriche di coerenza addizionali (angolo tra normali, deviazione di riproiezione).

## License
All rights reserved.

This software and all associated files are the exclusive property of Angelo Milella - COMAU.
Unauthorized copying, modification, distribution, or use of this software, via any medium, is strictly prohibited.

For inquiries about licensing, please contact: <angelo_milella_dev@yahoo.com>.
