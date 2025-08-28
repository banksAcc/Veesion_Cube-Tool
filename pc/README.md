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
  log_level: INFO      # DEBUG, INFO, WARNING, ERROR
  log_to_file: false
```

## Configuration (`app/config.yaml`)
- `ble.name_prefix` or `ble.addr` – select the ESP32 device
- `capture.frequency_ms` – interval between frames
- `capture.use_camera` – true for real camera, false for test mode
- `capture.camera_id` – OpenCV index or Basler serial
- `capture.image_format` – `jpg`, `png`, `tiff`
- `capture.tiff_compression` – `none`, `lzw`, `deflate`, `packbits`
- `pose.enabled` – enable pose processing
- `pose.cube` – dictionary, marker size, cube size, pairing strategy
- `pose.camera_calibration_npz` – path to intrinsics and distortion data
- `runtime.debug` / `runtime.log_to_file` – logging options

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

## Capture modes
- **Real camera:** `capture.use_camera: true`
- **Test mode:** `capture.use_camera: false` – images are copied from `capture.test_source_dir`.

Basler cameras are supported via the [pypylon](https://github.com/basler/pypylon) backend; ensure the SDK is installed and supply the desired serial number as `capture.camera_id`.

## Pose estimation
The worker reads finished sessions and computes cube/pen poses using the calibration file.  
Results are written next to the session folder in JSON format. See [`../cube_minimal/README.md`](../cube_minimal/README.md) for algorithm details.

### Logging & Debug
- Each session writes a **`session.log`** in its own folder.
- Log messages are prefixed by component (e.g., `[BLE]`, `[CAPTURE]`) and respect the verbosity from `runtime.log_level`.
- Available levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`. Adjust `runtime.log_level` in `config.yaml` and restart the app to change verbosity.
- Enable `runtime.log_to_file: true` to also write a global log file (`app.log`).
- Inconsistent state (START/START, END/END) is reported on console but does not stop the pipeline.

## License
All rights reserved.

This software and all associated files are the exclusive property of Angelo Milella - COMAU.
Unauthorized copying, modification, distribution, or use of this software, via any medium, is strictly prohibited.

For inquiries about licensing, please contact: <angelo_milella_dev@yahoo.com>.
