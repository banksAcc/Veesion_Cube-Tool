# ESP32 BLE Controller with RGB LED and OLED Display

Firmware for an ESP32 DevKit that exposes a BLE interface to trigger image
capture on a PC. It includes user feedback via a common-anode RGB LED and a
128x64 I2C SSD1306 OLED display, plus two physical buttons.

## Prerequisiti software

- **Arduino IDE 2.3.x**: https://www.arduino.cc/en/software
- **Pacchetto schede ESP32 2.0.14** (aggiungi `https://dl.espressif.com/dl/package_esp32_index.json` in File > Preferenze > URL per Gestore Schede)
- **Librerie consigliate** (Library Manager):
  - NimBLE-Arduino 1.4.1 — https://github.com/h2zero/NimBLE-Arduino
  - Adafruit SSD1306 2.5.13 — https://github.com/adafruit/Adafruit_SSD1306
  - Adafruit GFX Library 1.11.9 — https://github.com/adafruit/Adafruit-GFX-Library
- **arduino-cli 0.35.x** (facoltativo, per build da terminale): https://arduino.github.io/arduino-cli/latest/installation/
- **PlatformIO Core 6.1.x** (facoltativo, VS Code o CLI): https://docs.platformio.org/en/latest/core/installation.html

## Hardware

- **ESP32 DevKit** (ESP-WROOM-32)
- **RGB LED (common anode)** with resistors on the cathodes
- **SSD1306 OLED** display (128x64, I2C address 0x3C)
- **Two push buttons** using `INPUT_PULLUP`

### Connections

- **OLED**: SDA -> GPIO21, SCL -> GPIO22, VCC=3.3V, GND
- **LED RGB**: R=GPIO15, G=GPIO5, B=GPIO4 (anode to +5V)
- **Buttons**: BTN_EVENT -> GPIO16, BTN_BLE -> GPIO17

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
- **SENDING**: shows `Sending...`
- **BLE RX messages**: `COMPUTATION START` displays a banner, `COMPUTATION END` removes it

### Buttons

- **BTN_BLE (GPIO17)**:
  - Long press >= 4 s -> toggle BLE on/off (disconnect if connected)
  - Short press < 4 s -> disconnect and return to advertising
- **BTN_EVENT (GPIO16)**:
  - Press -> send `START\n`, LED goes red, display `Sending...`
  - Release -> send `END\n`

## Software Structure

- `main.ino` orchestrates buttons, BLE and UI
- `config.h` pin definitions and parameters
- `LedManager.*` RGB LED effects (inverted for common anode)
- `DisplayManager.*` SSD1306 display management
- `BleManager.*` NimBLE-Arduino wrapper (UART-like service)
- `Buttons.h` debounce and short/long press detection

## Notes

- LEDC PWM: 5 kHz, 12-bit resolution, global brightness limited to 10%
- Display powers off physically when BLE is off
- BLE messages are trimmed and uppercased for robustness

## Apertura del progetto

**Arduino IDE**

1. Avvia Arduino IDE e verifica che il pacchetto ESP32 sia installato (Tools > Board > Boards Manager).
2. Seleziona `File > Apri...` e punta alla cartella `esp32/src` (contiene `main.ino`).
3. Imposta `Tools > Board > ESP32 Dev Module` (o la scheda corrispondente al tuo DevKit).
4. Usa `Sketch > Include Library > Manage Libraries...` per installare/aggiornare le librerie consigliate alle versioni indicate.
5. Collega l'ESP32, scegli la porta corretta da `Tools > Port` e compila o carica normalmente.

**PlatformIO (VS Code o CLI)**

1. Apri la cartella `esp32` come workspace.
2. Se il file `platformio.ini` non esiste, crealo nella root `esp32` con il contenuto seguente:

   ```ini
   [env:esp32dev]
   platform = espressif32
   board = esp32dev
   framework = arduino
   monitor_speed = 115200
   lib_deps =
     h2zero/NimBLE-Arduino@^1.4.1
     adafruit/Adafruit SSD1306@^2.5.13
     adafruit/Adafruit GFX Library@^1.11.9
   ```

3. Con PlatformIO IDE scegli `Open Project` e seleziona `esp32`.
4. Da terminale puoi inizializzare automaticamente con `pio project init --board esp32dev` (sovrascrivera un `platformio.ini` gia presente solo se specificato con `--overwrite`).

## Build e caricamento

**Arduino CLI**

```powershell
arduino-cli core install esp32:esp32
arduino-cli compile --fqbn esp32:esp32:esp32 esp32/src
arduino-cli upload --fqbn esp32:esp32:esp32 -p COM5 esp32/src
```

Sostituisci `COM5` con la porta seriale rilevata (`arduino-cli board list`). Aggiungi `--build-path build/esp32` se vuoi un percorso di output dedicato.

**PlatformIO**

```powershell
pio run
pio run -t upload
```

Usa `pio device list` per trovare la porta, oppure specifica `upload_port = COM5` in `platformio.ini`.

## Monitor seriale e logging BLE

**Console seriale**

```powershell
arduino-cli monitor -p COM5 -c baudrate=115200
pio device monitor -b 115200
screen /dev/ttyUSB0 115200
```

**Log BLE**

- App mobili come nRF Connect o LightBlue consentono di verificare advertising e notifiche.
- Da PC puoi usare la libreria Python `bleak` per ricevere/loggare i messaggi BLE UART.

Esempio di script minimale (Linux/macOS/Windows, sostituisci `DEVICE_ADDRESS` con l'indirizzo del tuo ESP32):

```python
import asyncio
from bleak import BleakClient

UART_TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # Notify characteristic
UART_RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # Write characteristic

async def main():
    async with BleakClient("DEVICE_ADDRESS") as client:
        await client.start_notify(UART_TX, lambda _, data: print("[RX]", data.decode().strip()))
        await client.write_gatt_char(UART_RX, b"START\n")
        await asyncio.sleep(5)
        await client.write_gatt_char(UART_RX, b"END\n")

asyncio.run(main())
```

## Personalizzazione via `config.h`

Il file `esp32/src/config.h` centralizza pin e parametri principali:

- Aggiorna `PIN_LED_R`, `PIN_LED_G`, `PIN_LED_B` per adeguare il cablaggio del tuo LED.
- Modifica `PIN_BTN_EVENT`, `PIN_BTN_BLE` e `BLE_LONG_MS` per pulsanti e durata del long press.
- Cambia `I2C_SDA_PIN`, `I2C_SCL_PIN`, `OLED_ADDR`, `OLED_WIDTH`, `OLED_HEIGHT` se usi bus o display differenti.
- Regola `LED_BRIGHTNESS`, `LED_PWM_FREQ` e `LED_PWM_RES` se desideri effetti luminosi differenti.

Per personalizzare il nome BLE trasmesso:

1. Aggiungi in `config.h` (sotto gli altri define):

   ```cpp
   #define BLE_DEVICE_NAME "ESP32-RGB-BLE"
   ```

2. Sostituisci in `esp32/src/main.ino` la riga `BLE.begin("ESP32-RGB-BLE");` con `BLE.begin(BLE_DEVICE_NAME);`.

In questo modo potrai aggiornare il nome pubblicato senza toccare altre parti del codice.

## Verifica BLE con un client

1. Metti l'ESP32 in advertising (LED blu pulsante, display `STATUS: FREE`).
2. Avvia uno scanner BLE (nRF Connect, LightBlue, `bleak` con `python -m bleak discover`).
3. Verifica che il nome trasmesso corrisponda a quello impostato in configurazione.
4. Connettiti e osserva le notifiche sulla caratteristica UART (`6e400003-...`). I messaggi `START`/`END` devono apparire durante la pressione del pulsante evento.
5. Invia `START\n` e `END\n` dal client per verificare la gestione RX (sul Serial Monitor vedrai i log `[BLE] RX: ...`).

## Test rapido

1. Collega LED e display secondo lo schema della sezione Hardware, poi alimenta l'ESP32 via USB.
2. All'avvio il LED deve respirare in blu e l'OLED mostra `STATUS: FREE` con spinner.
3. Premendo il pulsante evento il LED diventa rosso, il display mostra `Sending...` e il log seriale riporta `[BLE] TX: START` / `[BLE] TX: END`.
4. Premendo a lungo il pulsante BLE (>= 4 s) il modulo si disconnette: LED spento, display `BLE OFF` che dopo 1 s si spegne.
5. Rilascia il pulsante BLE per tornare in advertising e verifica da un client BLE che le notifiche vengano nuovamente ricevute.

## Getting Started

1. Installa le librerie tramite Library Manager (`NimBLE-Arduino`, `Adafruit SSD1306`, `Adafruit GFX`).
2. Cabla i componenti come descritto sopra.
3. Compila e carica usando `ESP32 Dev Module` o l'ambiente PlatformIO.
4. Connettiti con un client BLE per inviare e ricevere messaggi.

## License
All rights reserved.

This software and all associated files are the exclusive property of Angelo Milella - COMAU
Unauthorized copying, modification, distribution, or use of this software, via any medium, is strictly prohibited.

For inquiries about licensing, please contact: <angelo_milella_dev@yahoo.com>.
