# ArUco Pen Pose — BLE-triggered capture and pose estimation

This project provides a hardware and software stack to capture images and
estimate the pose of a 3D printed pen tip equipped with ArUco markers. An
ESP32 inside the pen sends a BLE trigger to the PC, which then acquires an
image from a camera (industrial cameras such as **Basler** or any webcam are
supported) and computes the pose of the pen tip relative to the camera.

## TL;DR

- **Hardware**: 3D pen with a cube carrying ArUco markers and an ESP32 BLE
  trigger.
- **ESP32**: sends BLE notification to the PC when a button is pressed.
- **PC App**: receives the trigger, captures an image, detects ArUco markers
  and uses `solvePnP` to calculate the pen tip pose.
- **Output**: pose in the `camera_frame` and optional conversion to
  `world_frame` or `robot_frame`.

## Installation

```bash
pip install .
# or from PyPI
pip install cube-minimal
```

## Architecture

1. User presses a button on the pen (ESP32).
2. ESP32 publishes a BLE event.
3. The PC BLE listener receives the event and triggers image capture.
4. The PC vision pipeline:
   - Detects ArUco markers (configurable dictionary).
   - Reconstructs the cube pose with `cv::solvePnP`.
   - Applies the known rigid transform from cube center to pen tip.
5. Output: pen tip position/orientation and timestamp.
6. (Future) forward the pose to a robotic arm controller.

## Bill of Materials

- ESP32 with BLE (e.g. ESP32‑WROOM)
- LiPo battery and switch
- Two buttons (trigger / function)
- 3D printed pen body and cube for 3–4 ArUco markers
- Camera: webcam or industrial camera such as **Basler**
- Charuco or chessboard for camera calibration

## Key Concepts

### Markers & Pose

- ArUco markers placed on a cube; at least three must be visible.
- With known 3D coordinates of cube corners the pose is recovered via
  `solvePnP`.

### Tip Offset

- Define the rigid transform `T_cube->tip` (offset in cube frame).
- Tip pose in camera frame: `p_tip = R_cube * offset + t_cube`.

### Frames

- `camera_frame`: primary output
- `world_frame` (optional): estimated from a visible board
- `robot_frame` (future): known `T_world->robot` for robot control

## Software Stack

- **ESP32 firmware** (Arduino/NimBLE): BLE GATT, button handling, battery
  awareness
- **PC application** (Python):
  - OpenCV (ArUco, Charuco, solvePnP)
  - Bleak for BLE
  - Camera capture via OpenCV or vendor SDKs (e.g. Basler pypylon)

## Repository Structure

```

aruco-pen-pose/
├─ esp32/                # ESP32 firmware
├─ pc/                   # PC application
├─ stl/                  # 3D printable parts
└─ readme.md             # this file

## Quick Start

1. **ESP32 firmware**: open `esp32/` with Arduino IDE or PlatformIO, configure
   BLE device name and UUIDs in `config.h` and upload.
2. **PC App**:
   ```bash
   cd pc
   python -m venv .venv
   source .venv/bin/activate
   pip install -r app/requirements.txt
   ```
3. **Camera calibration**: print a Charuco or chessboard and run the provided
   script to compute `camera_intrinsics.yaml` and `camera_distortion.yaml`.
4. **Tip transform**: measure or estimate the offset from cube center to pen
   tip and store it in `tip_transform.yaml`.
5. **Run**:
   ```bash
   python app/app.py --ble-name ARU-PEN --camera 0 --dict DICT_4X4_50 --marker-size-mm 20.0
   ```

## License

MIT License. See individual folders for further details.

