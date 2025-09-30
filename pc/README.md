# ESP32 BLE Trigger -> PC Capture & Pose Pipeline

## Overview
This directory hosts the Python application that listens for BLE triggers from an ESP32 device, captures images, and performs optional cube pose estimation.

## Features
- Start or stop capture sessions from a physical ESP32 button.
- Store LZW-compressed TIFF frames in timestamped session folders for later inspection.
- Asynchronously estimate cube pose with OpenCV-based workers.
- Support webcams or industrial cameras such as Basler via `pypylon`.

## Prerequisites
- Python 3.10 or newer available on the system `PATH`.
- `pip` for installing Python dependencies.
- Optional Basler Pylon drivers and the `pypylon` package when using Basler cameras.
- BLE tooling (BlueZ on Linux, native stack on Windows/macOS) to pair the ESP32.

## Project Structure
```
app/
  app.py               # application entry point
  ble_client.py        # BLE connection and message handling
  capture.py           # camera acquisition or simulated frame sourcing
  click_test.py        # quick script to validate BLE button callbacks
  config.yaml          # runtime configuration
  pose_worker.py       # asynchronous pose computation
  requirements.txt
  session_manager.py   # session lifecycle management

calib/                  # sample calibration data
captures/               # capture sessions written here
image_to_be_used/       # sample dataset for simulated mode
```

## Installation
Run the commands from the `pc/` directory.

### Linux/macOS (bash/zsh)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r app/requirements.txt
```

### Windows (PowerShell)
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r app\requirements.txt
```

Deactivate the virtual environment with `deactivate` when you are done.

## Quick Configuration
1. Copy `app/config.example.yaml` to `app/config.yaml` if the example file is available. Otherwise duplicate the existing `config.yaml` before editing.
2. For simulated runs, set `capture.simulate_camera: true` and point `capture.test_source_dir` to `../image_to_be_used` or another folder with sample frames.
3. For real hardware, set `capture.simulate_camera: false`, choose `capture.camera_type` (`webcam`, `ip`, `basler`, etc.), and configure `capture.camera_id`, `capture.camera_serial`, or `capture.camera_ip` as required.
4. Confirm `pose.camera_calibration_npz` points to a valid calibration file inside `calib/`.
5. Adjust logging preferences with `runtime.log_level` and `runtime.log_to_file` if you need more diagnostics.

## Execution
- Simulated mode (no camera): ensure `capture.simulate_camera: true`, then run
  ```bash
  python app/app.py
  ```
- Real camera mode: set `capture.simulate_camera: false`, install any manufacturer drivers (for Basler, install Pylon and `pip install pypylon`), then execute
  ```bash
  python app/app.py
  ```
- Quick BLE test: validate button presses and logging without the full pipeline using
  ```bash
  python app/click_test.py
  ```

## Test and Debug
- Each capture session writes a `session.log` file inside the session folder under `captures/`.
- Global logging can be enabled with `runtime.log_to_file: true`, producing `app.log` in the project root.
- Raise verbosity by setting `runtime.log_level` to `DEBUG`, then restart the application to reload the configuration.
- BLE connection states, capture errors, and pose worker issues are all reported in the logs for post-mortem analysis.

## Key Parameters
| Parameter | Section | Purpose | Example |
| --- | --- | --- | --- |
| `capture.frequency_ms` | `capture` | Interval between frame acquisitions in milliseconds. | `200` |
| `capture.simulate_camera` | `capture` | Toggle between simulated datasets and live cameras. | `true` |
| `capture.test_source_dir` | `capture` | Directory for sample frames when simulating. | `../image_to_be_used` |
| `pose.method` | `pose` | Select the pose solver (`cube`, `custom`). | `cube` |
| `pose.max_parallel_jobs` | `pose` | Limit concurrent pose computations. | `3` |
| `runtime.log_level` | `runtime` | Set logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). | `INFO` |
| `runtime.log_to_file` | `runtime` | Enable writing aggregated logs to `app.log`. | `false` |

Pose results are saved alongside session folders. Refer to `../cube_minimal/README.md` for details on interpreting the cube pose output and validating calibration.

## License
All rights reserved.

This software and all associated files are the exclusive property of Angelo Milella - COMAU.
Unauthorized copying, modification, distribution, or use of this software, via any medium, is strictly prohibited.

For inquiries about licensing, please contact: <angelo_milella_dev@yahoo.com>.
