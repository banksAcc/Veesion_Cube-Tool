# ESP32 BLE Controller con LED RGB e Display OLED

## Panoramica
Questo progetto implementa un **controller BLE basato su ESP32 DevKit**, con:
- **LED RGB a anodo comune** come indicatore di stato.
- **Display OLED SSD1306 128x64 I²C** per la visualizzazione dello stato e messaggi.
- **Due pulsanti fisici** per la gestione della connessione BLE e per l’invio di eventi.

Il sistema permette di:
- Accendere/spegnere il BLE con pressioni lunghe (≥4s) sul pulsante BLE.
- Disconnettere rapidamente il dispositivo BLE con una pressione breve (<4s).
- Mostrare in tempo reale lo stato del sistema su LED e Display.
- Inviare messaggi START/END verso il centrale BLE con l’altro pulsante.
- Visualizzare messaggi in arrivo (es. avvio/fine calcolo posa).

---

## Hardware

### Componenti principali
- **ESP32 DevKit** (ESP-WROOM-32)
- **LED RGB anodo comune 5V** con resistenze sui catodi.
- **Display OLED SSD1306** (128x64 px, I²C, indirizzo 0x3C).
- **Due pulsanti a pressione** collegati a GPIO con `INPUT_PULLUP`.

### Collegamenti
- **OLED**: SDA → GPIO21, SCL → GPIO22, VCC=3.3V, GND.
- **LED RGB**:
  - Anodo comune a +5V con resistenze sui catodi.
  - R=GPIO15, G=GPIO5, B=GPIO4.
- **Pulsanti**:
  - BTN_EVENT → GPIO16 (gestione START/END).
  - BTN_BLE → GPIO17 (gestione BLE ON/OFF e disconnessione).

---

## Logica di funzionamento

### LED RGB
- **ADV (advertising)**: LED blu scuro con effetto *breathing* (fade in/out).  
- **CONNECTED**: LED verde fisso (intensità 10%).  
- **ARMING (pressione BTN17)**: LED giallo oro lampeggiante rapido.  
- **SENDING (evento in corso)**: LED giallo tenue fisso.  
- **EVENT_RED (BTN16 premuto, solo se connesso)**: LED rosso tenue.  
- **OFF**: LED spento.

### Display OLED
- **BLE ON (advertising)**: mostra `STATUS: FREE` + spinner animato + icona batteria.  
- **CONNECTED**: mostra `STATUS: OK` + icona batteria.  
- **DISCONNECTED / OFF**: mostra `BLE OFF`, display spento dopo 1s.  
- **SENDING**: mostra `Invio` con puntini animati.  
- **RX messaggi BLE**: 
  - `COMPUTATION START` → banner in alto `Pose Exti`.  
  - `COMPUTATION END` → rimuove banner.  

### Pulsanti
- **BTN_BLE (GPIO17)**:
  - Pressione lunga ≥4s → toggle BLE ON/OFF (con disconnect se connesso).
  - Pressione breve <4s → disconnette e torna in advertising.
- **BTN_EVENT (GPIO16)**:
  - Alla pressione → invia `START\n`, LED rosso tenue (se connesso), display `Invio…`.
  - Al rilascio → invia `END\n`, ritorno allo stato precedente.

---

## Struttura software

### File principali
- `main.ino` – orchestratore: gestisce logica dei pulsanti e richiama i manager.  
- `config.h` – definizioni pin e parametri (PWM, brightness, I²C).  
- `LedManager.{h,cpp}` – gestione effetti LED RGB con PWM (inversione per anodo comune).  
- `DisplayManager.{h,cpp}` – gestione display SSD1306 (stati, animazioni, icone).  
- `BleManager.{h,cpp}` – wrapper su NimBLE-Arduino (service UART-like).  
- `Buttons.h` – debounce e gestione eventi dei pulsanti.  
- `UiState.h` – enum degli stati UI.

### Librerie necessarie
- **NimBLE-Arduino** (BLE leggero).  
- **Adafruit SSD1306**.  
- **Adafruit GFX**.

---

## Note tecniche
- PWM LEDC: frequenza 5 kHz, risoluzione 12 bit, luminosità globale limitata al 10%.  
- Display OLED: acceso solo se BLE attivo; spento fisicamente dopo 1s da OFF.  
- Gestione robusta dei pulsanti con debounce + rilevamento short/long press.  
- RX BLE normalizzato (`trim` + `uppercase`) per robustezza.

---

## Come replicare
1. Installare librerie da Library Manager: `NimBLE-Arduino`, `Adafruit SSD1306`, `Adafruit GFX`.  
2. Collegare i componenti come descritto in sezione hardware.  
3. Caricare il firmware con board **ESP32 Dev Module**.  
4. Usare un’app BLE o un centrale per connettersi e inviare/leggere i messaggi.

---

## Stato del progetto
- **Funzionale** con logiche LED+Display integrate.  
- In arrivo: lettura reale livello batteria e visualizzazione percentuale.  
- Possibili estensioni: invio di pacchetti dati più complessi, interfaccia web via Wi-Fi.

---

## Autori
Progetto sviluppato come collaborazione di ingegneria elettronica, informatica e firmware.  
Obiettivo: documentare e replicare un **sistema BLE ESP32 con UI visiva**.
