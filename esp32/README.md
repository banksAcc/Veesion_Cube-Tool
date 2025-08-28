# ESP32 BLE Controller with RGB LED and OLED Display

Firmware for an ESP32 DevKit that exposes a BLE interface to trigger image
capture on a PC. It includes user feedback via a common-anode RGB LED and a
128×64 I²C SSD1306 OLED display, plus two physical buttons.

## Hardware

- **ESP32 DevKit** (ESP-WROOM-32)
- **RGB LED (common anode)** with resistors on the cathodes
- **SSD1306 OLED** display (128×64, I²C address 0x3C)
- **Two push buttons** using `INPUT_PULLUP`

### Connections

- **OLED**: SDA → GPIO21, SCL → GPIO22, VCC=3.3V, GND
- **LED RGB**: R=GPIO15, G=GPIO5, B=GPIO4 (anode to +5V)
- **Buttons**: BTN_EVENT → GPIO16, BTN_BLE → GPIO17

## Behaviour

### LED States

- **ADV (advertising)**: blue breathing effect
- **CONNECTED**: solid green
- **ARMING (BTN17 press)**: fast yellow blink
- **SENDING**: solid dim yellow
- **EVENT_RED**: red while BTN16 is pressed and connected
- **OFF**: LED off

### OLED Display

- **BLE ON (advertising)**: shows `STATUS: FREE` with spinner
- **CONNECTED**: shows `STATUS: OK`
- **DISCONNECTED/OFF**: shows `BLE OFF`, then turns off after 1 s
- **SENDING**: shows `Sending…`
- **BLE RX messages**: `COMPUTATION START` displays a banner, `COMPUTATION END`
  removes it

### Buttons

- **BTN_BLE (GPIO17)**:
  - Long press ≥4 s → toggle BLE ON/OFF (disconnect if connected)
  - Short press <4 s → disconnect and return to advertising
- **BTN_EVENT (GPIO16)**:
  - Press → send `START\n`, LED shows red, display `Sending…`
  - Release → send `END\n`

## Software Structure

- `main.ino` – orchestrates buttons, BLE and UI
- `config.h` – pin definitions and parameters
- `LedManager.*` – RGB LED effects (inverted for common anode)
- `DisplayManager.*` – SSD1306 display management
- `BleManager.*` – NimBLE-Arduino wrapper (UART-like service)
- `Buttons.h` – debounce and short/long press detection

## Notes

- LEDC PWM: 5 kHz, 12-bit resolution, global brightness limited to 10%
- Display powers off physically when BLE is off
- BLE messages are trimmed and uppercased for robustness

## Getting Started

1. Install libraries via the Arduino Library Manager: `NimBLE-Arduino`,
   `Adafruit SSD1306`, `Adafruit GFX`
2. Wire components as described above
3. Compile and upload using the **ESP32 Dev Module** board
4. Connect with a BLE central to send/receive messages

## License
All rights reserved.

This software and all associated files are the exclusive property of <Angelo Milella - COMAU>.
Unauthorized copying, modification, distribution, or use of this software, via any medium, is strictly prohibited.

For inquiries about licensing, please contact: <angelo_milella_dev@yahoo.com>.
