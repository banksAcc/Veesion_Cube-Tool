# ESP32 BLE Trigger → PC Capture & Pose Pipeline

This directory contains the Python application that listens for BLE triggers from the ESP32 pen and processes captured images.

## Features
- Connects to the ESP32 over BLE using `bleak`
- Captures frames from a Basler camera (via `pypylon`) or any OpenCV‑compatible webcam
- Stores images in time‑stamped sessions
- Runs an asynchronous pose‑estimation worker based on ChArUco/`cube_minimal`
- Test mode that replays images from a folder

## Project layout
```
app/
  app.py              # entry point
  ble_client.py       # BLE connection and callbacks
  capture.py          # camera or test-mode capture
  pose_worker.py      # asynchronous pose estimation
  session_manager.py  # start/stop sessions
  config.yaml         # configuration file
calib/
captures/
image_to_be_used/
```

## Installation
```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r app/requirements.txt
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

## Running
1. Power the ESP32 pen (it advertises over BLE).
2. Start the application:
   ```bash
   python app.py
   ```
3. Press the event button on the pen to start and stop a capture session.
   Each completed session is queued for pose estimation.

## Capture modes
- **Real camera:** `capture.use_camera: true`
- **Test mode:** `capture.use_camera: false` – images are copied from `capture.test_source_dir`.

Basler cameras are supported via the [pypylon](https://github.com/basler/pypylon) backend; ensure the SDK is installed and supply the desired serial number as `capture.camera_id`.

## Pose estimation
The worker reads finished sessions and computes cube/pen poses using the calibration file.  
Results are written next to the session folder in JSON format. See [`../cube_minimal/README.md`](../cube_minimal/README.md) for algorithm details.

## Troubleshooting
- **BLE pairing problems:** reset the OS Bluetooth stack and re-run the app.
- **Camera not found:** adjust `capture.camera_id` or verify the Basler driver.
- **Missing calibration:** ensure `pose.camera_calibration_npz` points to a valid `.npz`.

## License
MIT
