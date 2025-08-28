# ESP32 BLE Trigger → PC Capture & Pose Pipeline

This directory hosts the Python application that receives BLE triggers from an
ESP32 device and captures images for later pose estimation.

## Features

- Start/stop image capture sessions from a physical button on the ESP32.
- Save frames into timestamped sessions on disk.
- Asynchronously estimate the pose of a cube with ArUco markers using OpenCV.
- Works with webcams or industrial cameras such as Basler.

## Project Structure

```
app/
├─ app.py               # entry point
├─ ble_client.py        # BLE connection and message handling
├─ session_manager.py   # session lifecycle management
├─ capture.py           # camera acquisition or test image copy
├─ pose_worker.py       # asynchronous pose computation
├─ config.yaml          # configuration file
└─ requirements.txt

calib/                  # sample calibration data
captures/               # session output
```

### Installazione
Consigliato **virtual env**:
```powershell
# Windows PowerShell nella cartella pc_app/
py -m venv .venv
. .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
> Requisiti principali: `bleak`, `PyYAML`, `opencv-contrib-python`, `numpy`.

### Configurazione (`config.yaml`)
Esempio:
```yaml
ble:
  name_prefix: "ESP32-RGB-BLE"
  addr: null
  scan_timeout: 8.0

capture:
  frequency_ms: 200
  output_root: "captures"
  simulate_camera: false       # true = test mode (uses images from a folder)
  camera_type: "webcam"       # "webcam", "ip", etc.
  camera_id: 0
  camera_serial: null
  camera_ip: null
  image_format: "jpg"        # supported: jpg/png/tif/tiff
  jpeg_quality: 90
  tiff_compression: "lzw"    # optional
  test_source_dir: "test_images"
  stop_on_test_exhausted: false
  shuffle_test_images: false   # optional: randomize order
  stop_on_ble_disconnect: true
  keep_session_frames_on_error: true

pose:
  enabled: true
  method: "charuco"          # oppure "custom" (stub)
  max_parallel_jobs: 3
  delete_frames_after_processing: true
  results_format: "json"
  charuco:
    dictionary: "DICT_4X4_50"
    squares_x: 5
    squares_y: 7
    square_length_mm: 30.0
    marker_length_mm: 22.0
  camera_calibration_npz: "calibration.npz"
  # opzionale: se il .npz usa chiavi diverse
  calib_keys:
    K: "cameraMatrix"
    D: "distCoeffs"

runtime:
  debug: true
  log_to_file: false
```

### Esecuzione
- Accendi l’ESP32 (parte già in **advertising**).
- Avvia la app:
  ```powershell
  python app.py
  ```
- Premi **BTN16**: `START` all’**inizio** della pressione, `END` al **rilascio**.
- Al **END** la sessione viene messa in coda per la **pose** (in parallelo puoi già iniziare un nuovo `START`).

### Cattura: Camera reale vs Test mode
Scegli la strategia di cattura tramite `capture.use_camera` nel `config.yaml`:

- **Camera reale** (`true`): usa `cv2.VideoCapture(camera_id)` oppure, quando
  disponibile, l'integrazione Basler `pypylon` per camere industriali.
  Consigliato quando vuoi testare l'intera pipeline con hardware reale.
- **Test mode** (`false`): copia immagini da `test_source_dir` con cadenza
  `frequency_ms`. Ideale per debug, sviluppo offline o integrazione continua.
  Se le immagini finiscono:
  - `stop_on_test_exhausted: true` ⇒ **termina** la sessione.
  - `false` ⇒ **ricomincia** dall’inizio (ciclo).

Supporto **TIFF** con compressione opzionale LZW/Deflate, e **16-bit** (convertiti a 8-bit per ArUco).

### Stima di posa (ChArUco)
- Richiede **OpenCV contrib**.
- Parametri: `squares_x`, `squares_y` (numero di quadretti), `square_length_mm` (lato quadretto), `marker_length_mm` (lato marker ArUco).
- Calibrazione **camera** via `.npz`:
  - chiavi supportate: `camera_matrix`/`cameraMatrix`/`K`/`mtx` e `dist_coeffs`/`distCoeffs`/`D`/`dist` (configurabili con `calib_keys`).
- Output per frame: `ok`, `rvec`, `tvec`, `num_charuco`, `reproj_err`.  
  > `rvec`/`tvec` sono la posa **board→camera** (Rodrigues + traslazione, unità mm se la board è in mm).

### Formato output & naming
- Sessioni salvate in:  
  `captures/session_YYYY-mm-dd_HH-MM-SS__YYYY-mm-dd_HH-MM-SS/`
- Risultati posa:  
  `captures/session_..._pose.json`
- Se `delete_frames_after_processing=true` **e** `runtime.debug=false` ⇒ i frame della sessione vengono **rimossi** dopo il calcolo (lo JSON rimane).

### Logging & Debug
- Ogni sessione ha un **`session.log`** nella propria cartella.
- Logging su console; opzionalmente un log globale con `runtime.log_to_file: true` (puoi estendere facilmente con `logging` modulare).
- Stato incoerente (START/START, END/END) segnalato in console (non interrompe la pipeline).

### Troubleshooting
- **BLE non si connette**: spegni/riaccendi Bluetooth di sistema; chiudi app concorrenti (es. nRF Connect). Su Windows, lo script imposta automaticamente la **WindowsSelectorEventLoopPolicy**.
- **Non trova l’ESP**: usa `ble.addr` nel `config.yaml` (indirizzo stampato lato ESP su seriale) oppure aumenta `scan_timeout`.
- **Camera**: prova `camera_id: 1/2`; verifica di non avere la webcam occupata da altre app.
- **no_calibration**: controlla che il `.npz` contenga le chiavi giuste o usa `pose.calib_keys` per mappare i nomi (`cameraMatrix`, `distCoeffs`, ecc.).
- **Prestazioni**: TIFF/16-bit e risoluzioni elevate rallentano la detection; valuta downscale o JPEG qualità alta.

---

## Licenza
MIT
