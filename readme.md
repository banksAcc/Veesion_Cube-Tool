# ArUco Pen Pose — sistema penna+marker ArUco con trigger BLE e stima di posa

Sistema hardware/software per acquisire foto sincronizzate dal PC tramite trigger BLE inviato da un **ESP32** integrato in una **penna 3D** con un piccolo **cubo** stampato in 3D che monta **3/4 marker ArUco**.  
Il PC, alla ricezione dell’input, scatta la foto (es. da camera industriale tipo Basler o webcam), **stima la posa della punta** della penna e la espone per uso real‑time o per logging. In roadmap è prevista la **replicazione della posa** con un **braccio robotico**.

---

## ✨ TL;DR

- **Hardware**: penna 3D + cubo con marker ArUco + ESP32 (BLE) + pulsanti.  
- **ESP32**: invia trigger BLE → PC.  
- **PC App**: riceve trigger → scatta foto → detect ArUco → `solvePnP` → calcola posa della **punta** (offset noto dal cubo).  
- **Output**: posa in `camera_frame` + conversione opzionale in `world/robot_frame`.  
- **Roadmap**: streaming continuo, calibrazione semplificata, integrazione robot.

---

## 🧱 Architettura

1. **Utente preme un tasto** sulla penna (ESP32).
2. **ESP32 pubblica un evento BLE** (notifica/char write).
3. **PC Listener BLE** riceve l’evento → **trigga** la cattura immagine.
4. **PC Vision**:
   - Detect **ArUco** (dictionary configurabile).
   - Ricostruisce la posa del **cubo** con `cv::solvePnP`.
   - Applica la **trasformazione rigida** nota dal centro del cubo alla **punta** della penna.
5. **Output**: posizione/orientamento punta + timestamp + immagine (opzionale).
6. **(Futuro)** Invio posa al **controller del braccio robotico**.

---

## 🧩 Bill of Materials (BoM)

- **ESP32** con BLE (es. ESP32‑WROOM).  
- **Batteria LiPo** + interruttore.  
- **2 pulsanti** (scatto / funzione).  
- **Penna 3D** o corpo stampato.  
- **Cubo 3D** (stampa PLA/ABS) con sedi per **3–4 marker ArUco**.  
- **Camera**: webcam UVC o camera industriale (es. Basler) + illuminazione diffusa.  
- **Charuco o chessboard** per **calibrazione camera**.

---

## 🧠 Concetti chiave

### Marker & Posa
- Marker ArUco su un **cubo**: ogni faccia ospita un marker (almeno 3 visibili).  
- Dato l’elenco di corner 2D ↔ punti 3D noti, si usa `solvePnP` per ottenere **R, t** del cubo rispetto alla camera.

### Offset fino alla **punta**
- Misura/definisci una **trasformazione rigida** `T_cubo→punta` (vettore offset 3D nel frame del cubo).  
- La posa della punta nel frame camera:  
  `p_punta_cam = R_cubo_cam * p_offset_cubo + t_cubo_cam`  
- L’orientamento della penna può essere definito da un asse del cubo o da 2–3 punti di riferimento.

### Sistemi di riferimento
- `camera_frame`: output primario.  
- `world_frame` (opzionale): fissa una board a vista; stima `T_camera→world` per trasformare la punta nel mondo.  
- `robot_frame` (futuro): nota `T_world→robot`, trasferisci la posa al braccio.

---

## 🛠️ Software stack

- **Firmware ESP32 (Arduino/ESP‑IDF)**: BLE GATT, gestione pulsanti, battery-awareness.
- **PC App (Python)**:
  - **OpenCV** (ArUco, Charuco, solvePnP).
  - **Bleak** (BLE cross‑platform).
  - **Acquisizione camera**: OpenCV/SDK vendor.
  - CLI + opzione GUI minimale (in roadmap).

## 👨‍💻 Classi firmware ESP32

- `BleManager` – wrapper su NimBLE-Arduino per advertising, connessione e scambio messaggi.
- `DisplayManager` – gestisce il display SSD1306 (stati, animazioni).
- `LedManager` – controlla il LED RGB e i suoi effetti.
- `Buttons` – debounce e rilevamento pressioni brevi/lunghe.

---

## 📦 Struttura del repository

```
aru-pen-pose/
├─ esp32/
│  ├─ src/
│  └─ platformio.ini (o Arduino .ino)
├─ pc/
│  ├─ app/
│  │  ├─ main.py
│  │  ├─ ble_listener.py
│  │  ├─ camera.py
│  │  ├─ aruco_pose.py
│  │  ├─ tip_transform.yaml     # offset cubo→punta
│  │  └─ config.yaml
│  ├─ calib/
│  │  ├─ charuco_dict.yaml
│  │  ├─ camera_intrinsics.yaml
│  │  └─ camera_distortion.yaml
│  └─ requirements.txt
├─ stl/
│  ├─ cube_mount.stl
│  └─ pen_body.stl
├─ docs/
│  ├─ aruco_layout.pdf
│  └─ protocol_ble.md
└─ README.md
```

---

## 🚀 Setup rapido

### 1) Firmware ESP32
- Apri `firmware/esp32/` (Arduino IDE o PlatformIO).  
- Configura **device name BLE** e UUID delle caratteristiche in `config.h`.  
- Carica sul dispositivo.  
- Pulsante `SCATTO` → invia **notifica** BLE.

### 2) PC App (Python 3.10+)
```bash
cd pc
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r app/requirements.txt
```

### 3) Calibrazione camera
- Stampa una **Charuco** (consigliata) o chessboard.  
- Usa lo script (da fornire in `pc/app/`) per:
  - raccogliere immagini,
  - stimare **intrinseci** e **distorsioni** (`camera_intrinsics.yaml`, `camera_distortion.yaml`).

### 4) Definizione offset cubo→punta
- Misura in CAD o empiricamente l’offset 3D dal **frame del cubo** alla **punta**.  
- Salva in `tip_transform.yaml`, es.:
  ```yaml
  tip_offset_mm: [0.0, 15.2, -38.5]   # x,y,z nel frame del cubo
  ```

### 5) Avvio
```bash
python app/main.py   --ble-name ARU-PEN   --camera 0   --dict DICT_4X4_50   --marker-size-mm 20.0
```

---

## 🔗 Protocollo BLE (proposta)

- **Service UUID**: `12345678-0000-0000-0000-1234567890ab`  
- **Characteristic (Notify)**: `12345678-0000-0000-0000-1234567890ac`  
- **Payload (little‑endian)**:
  ```
  u8 event_type   # 0x01 = TRIGGER
  u32 tick_ms
  u8 battery_pct
  u8 button_id    # 1=SCATTO, 2=ALTRO
  ```
- Il PC sottoscrive la characteristic → ad ogni notifica esegue `capture()`.

---

## 🎯 Rilevamento ArUco & PnP

- **Dictionary**: `DICT_4X4_50` (default, configurabile).  
- **Dimensioni marker**: es. 20 mm (definisci esatto in `--marker-size-mm`).  
- **Punti 3D**: definisci i corner nel **frame del cubo** (per ogni faccia montata).  
- **solvePnP**: `cv::solvePnP(objectPoints, imagePoints, K, dist, R, t)`.  
- **Punta**: `p_punta = R * offset + t`.  
- **Output**: JSON su stdout o su socket:
  ```json
  {
    "ts": 1723545600.123,
    "tip_position_camera_mm": [x, y, z],
    "tip_orientation_Rvec": [rx, ry, rz],
    "visibility_markers": 3,
    "image_path": "captures/2025-08-13_17-22-10.png"
  }
  ```

---

## 🧪 Test & Debug

- **Modalità test** senza BLE: `--test-mode` → scatti manuali (tasto o timer).  
- **Overlay**: disegna assi, ID marker, reprojection error medio.  
- **Log**: CSV con posa e residui PnP.

---

## 🤖 Integrazione robot (roadmap)

- Pubblica la posa su **ROS 2** o ZeroMQ.  
- Definisci `T_camera→world` (board fissa) e `T_world→robot`.  
- Implementa **filtro** (Kalman/EMA) e **rate limiter**.  
- Aggiungi **hand‑eye calibration** se la camera è sul polso del robot.

---

## 📐 Consigli meccanici

- Mantieni **rigide** le distanze cubo↔punta.  
- Allinea una faccia del cubo all’asse della penna per ridurre ambiguità.  
- Evita riflessi sui marker (stampa opaca / adesivi matte).

---

## 🔒 Sicurezza & uso

- Evita puntamento verso occhi (punta): **DPI** se necessario.  
- Assicurati che il robot lavori in area sicura (interlock, e‑stop).  
- Logga sempre gli errori di detection e i fallimenti PnP.

---

## 📜 Licenza

MIT (o altra a tua scelta). Inserisci il file `LICENSE`.

---

## 🗺️ Roadmap

- [ ] GUI minimale per preview e conferma scatto  
- [ ] Streaming posa a 30 FPS (modalità continua)  
- [ ] Autocalibrazione offset cubo→punta da 3 pose note  
- [ ] Integrazione ROS 2 / MoveIt  
- [ ] Test multi-camera e fusion

---

## 🤝 Contributi

PR e issue benvenuti. Apri una issue con:
- log, versione, OS, camera usata, foto esempio, file di calibrazione.
