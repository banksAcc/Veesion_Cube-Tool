# Veesion Cube Tool

A compact hardware and software stack for estimating the pose of a 3D‑printed pen tip.  
An ESP32 inside the pen sends a BLE trigger; the PC listens for the event, grabs a frame from a camera and computes the pen pose from ArUco markers.

![License](https://img.shields.io/badge/license-Proprietary-red)
![Python](https://img.shields.io/badge/python-3.10+-blue)
![C++](https://img.shields.io/badge/firmware-ESP32-green)
![PlatformIO](https://img.shields.io/badge/build-PlatformIO-orange)
![OpenCV](https://img.shields.io/badge/OpenCV-4.8+-brightgreen)

## Idea
<div style="display: flex; gap: 20px;">
  <img src="esp32/img/example_nobg_2.png" alt="Device" width="400"/>
  <img src="pc/captures/session_2025-08-28_13-39-13__2025-08-28_13-39-13/img_for_readme.png" alt="Cube After" width="400"/>
</div>
<div style="display: flex; alling: center">
  <img src="stl/image/pen and marker 2.png" alt="3D pen" width="200"/>
</div>

## Prerequisites

### Hardware
- **ESP32 DevKit** (BLE + two buttons) to trigger the acquisition
- **Physical assembly**: 3D-printed pen/cube with 3–4 ArUco markers attached
- **Camera**: Basler camera with Pylon drivers installed or a compatible UVC webcam
- **Calibration target**: ChArUco board or checkerboard pattern

### Software
- **Python ≥3.10** and `pip` to install dependencies
- **ESP32 firmware toolchain**: Arduino IDE/CLI or PlatformIO (optional but recommended)
- **Basler Pylon drivers** (optional) for industrial camera integration
- Python libraries from [`pc/app/requirements.txt`](pc/app/requirements.txt)

## Repository structure
- [`esp32/`](esp32/) – BLE firmware for the pen, detailed in [`esp32/README.md`](esp32/README.md)
- [`pc/`](pc/) – PC-side application for capture and pose estimation, see [`pc/README.md`](pc/README.md)
- [`cube_minimal/`](cube_minimal/) – pose estimation library with dataset and tests
- [`cube_minimal/data/sample_dataset/`](cube_minimal/data/sample_dataset/) – sample images referenced in [Quick start](#quick-start)

## Workflow
1. Press a button on the pen. The ESP32 publishes a BLE notification.
2. The PC application receives the trigger and acquires an image from the selected camera.
3. ArUco markers on the cube are detected and the cube pose is estimated.
4. A fixed transform gives the pen‑tip pose, which can be logged or streamed.

## Quick start

### Set up the PC environment
```bash
cd pc
python -m venv .venv
source .venv/bin/activate
pip install -r app/requirements.txt
```
```powershell
cd pc
py -m venv .venv
. .\.venv\Scripts\Activate.ps1
pip install -r app\requirements.txt
```
> Tip: keep the virtual environment active for the next steps (`pytest`, CLI, PC application).

### Build & flash the ESP32 firmware
Follow the [Getting Started](esp32/README.md#getting-started) section of the firmware:

1. Install the **NimBLE-Arduino**, **Adafruit SSD1306**, and **Adafruit GFX** libraries via the Arduino Library Manager.
2. Wire the components as described in [`esp32/README.md`](esp32/README.md#connections).
3. Build and upload the project by selecting the **ESP32 Dev Module** board (Arduino IDE/CLI) or set up an equivalent PlatformIO project.

### Calibration and sample dataset
- Use the scripts in [`pc/calib/`](pc/calib/) to produce `calib_data.npz` (camera intrinsics) from a ChArUco/checkerboard target.
- For quick trials, point `capture.test_source_dir` to [`cube_minimal/data/sample_dataset/`](cube_minimal/data/sample_dataset/), which contains the sample images described in its [README](cube_minimal/data/README.md).

### Run the pipeline quickly
```bash
cd pc/app
python app.py
```
Configure [`config.yaml`](pc/app/config.yaml) before launching the application: set `ble.name_prefix` or `ble.addr`, choose the camera (`camera_type`, `camera_id`/`camera_serial`), and provide the calibration path (`pose.camera_calibration_npz`).

#### Simulated mode
For tests without physical hardware, set in `config.yaml`:

```yaml
capture:
  simulate_camera: true
  test_source_dir: "../cube_minimal/data/sample_dataset"
```
This mode replays sessions by reading the sample images through the same processing pipeline.

## Rapid validation
- **Python tests** (`cube_minimal`):
  ```bash
  cd pc
  source .venv/bin/activate        # Linux/macOS
  # PowerShell: . .\.venv\Scripts\Activate.ps1
  pytest ../cube_minimal/tests
  ```
- **Single-image estimation CLI**:
  ```bash
  python -m cube_minimal.cli.estimate_one \
      --image cube_minimal/data/sample_dataset/example_1.png \
      --camera cube_minimal/config/calib_data.npz \
      --aruco_dict 4X4_50 \
      --marker_size 0.055 \
      --cube_size 0.060 \
      --out overlay.png
  ```
- **Simulated PC session**: enable `capture.simulate_camera: true` as above and launch the application from `pc/app/`:
  ```bash
  python app.py
  ```

## Further reading
- [Prerequisites](#prerequisites) and [Repository structure](#repository-structure) for a quick overview
- [`pc/README.md`](pc/README.md) – deep dive into the PC pipeline configuration and Basler parameters
- [`esp32/README.md`](esp32/README.md) – hardware details, LEDs, and buttons
- [`cube_minimal/README.md`](cube_minimal/README.md) – pose estimation API and CLI
- [`cube_minimal/data/README.md`](cube_minimal/data/README.md) – structure of the sample dataset

## License
All rights reserved.

This software and all associated files are the exclusive property of Angelo Milella - COMAU.
Unauthorized copying, modification, distribution, or use of this software, via any medium, is strictly prohibited.

For inquiries about licensing, please contact: <angelo_milella_dev@yahoo.com>.
