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

## Installation

```bash
cd pc
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r app/requirements.txt
```

Key dependencies: `bleak`, `PyYAML`, `opencv-contrib-python`, `numpy`.

## Configuration

Edit `app/config.yaml` to set the BLE device name or address, capture
frequency, camera ID (use 0 for default or the index for a Basler camera), and
other options such as image format or test mode.

## Usage

1. Power the ESP32 so it starts advertising.
2. Launch the application:
   ```bash
   python app/app.py
   ```
3. Press the event button: `START` on press, `END` on release. After `END` the
   session is queued for pose computation while you can start a new one.

### Capture Modes

- **Real camera**: `use_camera: true` → uses `cv2.VideoCapture` (Basler and
  generic webcams).
- **Test mode**: `use_camera: false` → copies images from `test_source_dir` at
  the configured rate.

### Pose Estimation

Pose results are written as JSON in the session directory. When
`delete_frames_after_processing` is `true` and `runtime.debug` is `false`, the
frames are removed after processing.

### Logging

Each session contains a `session.log` file with basic diagnostics. A global log
file can be enabled via `runtime.log_to_file`.

## License

MIT License.

