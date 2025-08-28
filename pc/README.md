# ESP32 BLE Trigger → PC Capture & Pose Pipeline

Sistema completo **ESP32 → BLE → PC** per:
- **Controllare** lo scatto di fotogrammi (start/stop) da un pulsante fisico su ESP32.
- **Salvare** i frame in sessioni temporali leggibili.
- **Lanciare in automatico** un job asincrono di **stima di posa** (ChArUco/OpenCV) sui frame appena acquisiti.
- **Gestire in parallelo** acquisizione (nuove sessioni) e calcolo posa (sessioni chiuse).

> Progetto diviso in due parti:
> 1) **Firmware ESP32** (Arduino + NimBLE-Arduino): gestisce 2 pulsanti e LED RGB (anodo comune), espone un servizio **BLE UART-like** e invia **START/END** al PC.
> 2) **PC App** (Python + bleak + OpenCV): si connette via BLE, **ascolta START/END**, scatta o copia frame a frequenza configurabile e calcola la **pose** (ChArUco).

---

## Indice
- [Hardware & Firmware ESP32](#hardware--firmware-esp32)
  - [Pinout LED & Pulsanti](#pinout-led--pulsanti)
  - [Stati LED (feedback utente)](#stati-led-feedback-utente)
  - [Logica Pulsante BLE (GPIO17)](#logica-pulsante-ble-gpio17)
  - [Logica Pulsante Evento (GPIO16)](#logica-pulsante-evento-gpio16)
  - [Protocollo BLE](#protocollo-ble)
  - [Build con PlatformIO](#build-con-platformio)
- [PC App (Python)](#pc-app-python)
  - [Struttura progetto](#struttura-progetto)
  - [Installazione](#installazione)
  - [Configurazione (`config.yaml`)](#configurazione-configyaml)
  - [Esecuzione](#esecuzione)
  - [Cattura: Camera reale vs Test mode](#cattura-camera-reale-vs-test-mode)
  - [Stima di posa (ChArUco)](#stima-di-posa-charuco)
  - [Formato output & naming](#formato-output--naming)
  - [Logging & Debug](#logging--debug)
  - [Troubleshooting](#troubleshooting)
- [Licenza](#licenza)

---

## Hardware & Firmware ESP32

### Pinout LED & Pulsanti
LED RGB **anodo comune** (logica invertita; HIGH = spento, LOW = acceso). PWM con **LEDC pin-based** (Arduino core 3.x).

- **LED**: `RED=GPIO15`, `GREEN=GPIO2` *(consigliato spostarlo a GPIO23)*, `BLUE=GPIO4`
- **Pulsanti** (entrambi con **INPUT_PULLUP**, pulsante verso GND):
  - `GPIO17`: tasto **BLE/Advertising**
  - `GPIO16`: tasto **Evento** (invia START/END)

> Nota: **GPIO2** è un *boot strap pin*. Per massima affidabilità sposta **GREEN** su **GPIO23** (o 21/22/25/26/27/32/33) e aggiorna il define nel firmware.

### Stati LED (feedback utente)
- **BOOT**: LED **spento** (boot dark).
- **ARMING (giallo lampeggiante)**: pressione in corso del tasto BLE (finestra 4s).
- **ADVERTISING (blu “breathing”)**: device visibile/scansionabile via BLE.
- **CONNECTED (verde fisso)**: connessione BLE attiva.
- **ERROR (rosso lampeggiante)**: stato di errore (non usato di default).

### Logica Pulsante BLE (GPIO17)
- **Durante la pressione**: LED **giallo lampeggiante** (stato *ARMING*).
- Se **CONNESSO (verde)**:
  - **rilascio < 4s** ⇒ **disconnette** e **LED OFF**.
  - **pressione ≥ 4s** ⇒ **disconnette** e **entra in advertising** (blu breathing).
- Se **ADVERTISING (blu)**:
  - **pressione ≥ 4s** ⇒ **stop advertising** ⇒ **LED OFF**.
  - **rilascio < 4s** ⇒ annulla, resta in advertising.
- Se **OFF**:
  - **pressione ≥ 4s** ⇒ **start advertising**.

### Logica Pulsante Evento (GPIO16)
- **Pressione (edge falling)** ⇒ invia **`START\n`**.
- **Rilascio (edge rising)** ⇒ invia **`END\n`**.
- Se non connesso BLE, viene segnalato su seriale e con flash rosso (non invia).

### Protocollo BLE
- Servizio Nordic UART (NUS-like):
  - **TX** (ESP32→PC, Notify): `6E400003-B5A3-F393-E0A9-E50E24DCCA9E`
  - **RX** (PC→ESP32, Write/WriteNR): `6E400002-B5A3-F393-E0A9-E50E24DCCA9E` *(non usato ora)*
- **Messaggi** inviati dall’ESP32 via TX: `START\n`, `END\n`.

### Build con PlatformIO
Esempio `platformio.ini` minimal:
```ini
[env:esp32dev]
platform = espressif32
board = esp32dev
framework = arduino
upload_speed  = 115200
monitor_speed = 115200
lib_deps = h2zero/NimBLE-Arduino @ ^2.0.0
; board_build.partitions = huge_app.csv
```
## PC App (Python)

### Struttura progetto
```
  app/
  ├─ app.py               # entrypoint
  ├─ ble_client.py        # connessione BLE + callback START/END
  ├─ session_manager.py   # gestione sessioni di scatto
  ├─ capture.py           # CameraCapture (OpenCV) / TestCapture (copy)
  ├─ pose_worker.py       # worker asincrono calcolo posa (ChArUco/custom)
  ├─ config.yaml          # configurazione
  └─ requirements.txt
  
  calib/
  └─ calib_data.npz       # matrice di calibrazione

  captures/

  image_to_be_used/
  
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
  use_camera: true
  camera_id: 0
  image_format: "jpg"        # supportati: jpg/png/tif/tiff
  jpeg_quality: 90
  tiff_compression: "lzw"    # opzionale
  test_source_dir: "test_images"
  stop_on_test_exhausted: false
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
