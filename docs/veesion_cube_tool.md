# Documento di sintesi del sistema Veesion Cube Tool

## Visione complessiva
Abbiamo progettato il Veesion Cube Tool come una piattaforma integrata hardware–software capace di stimare la posa tridimensionale della punta di un pennino dotato di marker ArUco. La catena inizia da un modulo **ESP32** incapsulato nell'oggetto fisico e termina nella pipeline software su PC che acquisisce fotogrammi, esegue la stima di posa e produce artefatti analitici (JSON, CSV, overlay). Il presente documento funge da base strutturata per la redazione della documentazione ufficiale: raccoglie le motivazioni progettuali, i componenti materiali e digitali, il flusso di elaborazione, le librerie riutilizzabili e gli strumenti ausiliari.

## Hardware e oggetto fisico
### Penna intelligente con ESP32
Abbiamo alloggiato un **ESP32 DevKit** all'interno di un corpo penna/cubo stampato in 3D. Il firmware, descritto in dettaglio in [`esp32/README.md`](../esp32/README.md), gestisce:
- una coppia di pulsanti (`BTN_EVENT`, `BTN_BLE`) per generare notifiche BLE (`START`/`END`) e per abilitare o disabilitare la radio;
- un LED RGB a catodo comune con codifica a stati (advertising blu, connessione verde, invio evento rosso/giallo);
- un display OLED SSD1306 per feedback testuale, utile durante sessioni di laboratorio;
- un protocollo BLE UART‐like implementato tramite NimBLE che invia comandi al PC e riceve notifiche di stato (`COMPUTATION START`/`END`).
I dettagli di cablaggio (GPIO21/22 per I²C, GPIO4/5/15 per il LED, GPIO16/17 per i pulsanti) e le note operative sono raccolti nel README citato. Il firmware vive nel sorgente [`esp32/src`](../esp32/src).

### Marcatori ArUco e corpo fisico
Il pennino monta un cubo con 5 marker ArUco, modellato tramite i file STL presenti in [`stl/`](../stl/). La geometria garantisce una distanza nota tra il centro del cubo e la punta: ciò alimenta la trasformazione rigida utilizzata dal PC per derivare la posa del tip partendo dal cubo. Le immagini dimostrative (`stl/image/example_1.png`, `example_2.png`) illustrano l'assemblaggio finale.

### Calibrazione e dataset di riferimento
Per le validazioni in laboratorio utilizziamo un target ChArUco/checkerboard per stimare gli intrinseci della camera. I file di configurazione campione sono in [`cube_minimal/config`](../cube_minimal/config) e [`pc/calib`](../pc/calib). Il dataset di immagini statiche usato nelle simulazioni e nei test è in [`cube_minimal/data/sample_dataset`](../cube_minimal/data/sample_dataset) e viene richiamato sia dalla CLI sia dal PC app in modalità `simulate_camera`.

## Pipeline software su PC
### Architettura generale
La directory [`pc/app`](../pc/app) ospita l'applicazione principale. Il flusso è orchestrato da tre componenti principali:
1. **Client BLE** – [`ble_client.py`](../pc/app/ble_client.py) scandisce o usa l'indirizzo fornito in configurazione, si connette all'ESP32 e inoltra i messaggi `START`/`END` al gestore di sessione. Lo stesso modulo mantiene un canale asincrono per inviare messaggi di ritorno verso l'hardware (ad esempio gli eventi `COMPUTATION START/END`).
2. **Session Manager** – [`session_manager.py`](../pc/app/session_manager.py) gestisce il ciclo di vita di ogni acquisizione. Alla ricezione di `START` crea un oggetto `Session` che sceglie il backend di cattura (`OpenCvCapture`, `PylonCapture` o `TestCapture`) in base alla configurazione (`capture.simulate_camera`). I fotogrammi vengono salvati facoltativamente e, soprattutto, vengono trasferiti in memoria a valle tramite `asyncio.Queue` sotto forma di `FramePacket` definiti in [`stream.py`](../pc/app/stream.py).
3. **Pose Worker** – [`pose_worker.py`](../pc/app/pose_worker.py) consuma la coda asincrona di pacchetti e invoca l'API di stima del cubo offerta dalla libreria `cube_minimal`. L'architettura multi‐thread (queue in memoria + `ThreadPoolExecutor`) ci consente di decouplare l'acquisizione dalla computazione mantenendo bassa la latenza.

Il file [`app.py`](../pc/app/app.py) collega le componenti precedenti, avviando l'event loop, la sessione BLE e la coda BLE per comunicare con il dispositivo. Il modulo [`config_models.py`](../pc/app/config_models.py) definisce la struttura tipizzata della configurazione (`AppConfig`), garantendo la validazione dei parametri presenti in [`config.yaml`](../pc/app/config.yaml).

### Flusso di una sessione
Quando l'ESP32 invia `START`, `SessionManager` crea una cartella `session_<timestamp>` con relativo `session.log`, lancia un thread di acquisizione e pone i `FramePacket` in coda. I pacchetti contengono frame BGR, nome file canonico, timestamp (sia float sia ISO) ed eventuale destinazione su disco se `capture.save_frames` è abilitato. Il worker di posa legge i pacchetti, invoca `_process_cube_frame` e popola una struttura `results` che verrà serializzata a fine sessione.

Alla ricezione di `END`, `SessionManager` chiude la sessione, notifica il worker tramite `PoseEndMessage` e attende la flush finale della coda. Il worker scrive due artefatti centrali:
- un JSON `<session>_pose.json` con tutti i frame elaborati (posizione e orientazione cubo, eventuali pose della punta);
- un CSV `<session>_pose.csv` con intestazioni `frame_index,timestamp,ok,tip_x,...,tip_rx`, dove gli angoli Euler sono espressi in radianti secondo la convenzione intrinseca Z–Y–X (funzione `_rotation_matrix_to_euler_zyx`).
Durante l'elaborazione il worker invia messaggi BLE `BLE_COMPUTATION_START/END` che il firmware può visualizzare sul display.

### Pipeline in memoria
Abbiamo scelto di mantenere l'intero flusso tra cattura e stima all'interno della RAM fino al punto di serializzazione finale. La classe `Session` spinge i frame in `asyncio.Queue` con capacità configurabile (`capture.frame_queue_size`); il worker li elabora in thread separato (`asyncio.to_thread`) e rilascia esplicitamente il riferimento all'immagine (`packet.frame = None`) subito dopo aver generato i risultati, evitando accumuli. Questa architettura minimizza l'I/O su disco e rende possibile la modalità `capture.save_frames = false` in cui nessun frame intermedio viene scritto.

## Libreria `cube_minimal`
### Struttura e API
La libreria, documentata in [`cube_minimal/README.md`](../cube_minimal/README.md), espone un'API ad alto livello tramite [`cube_pose/api.py`](../cube_minimal/cube_minimal/cube_pose/api.py). La funzione `estimate_cube_from_image` accetta un'immagine o un percorso, la calibrazione (`.npz` contenente `K` e `dist`), la dimensione dei marker e del cubo e una strategia di aggregazione delle facce (`pair_strategy`). Il flusso interno è:
1. caricamento dell'immagine e degli intrinseci (`load_camera`);
2. rilevazione ArUco (`detect_markers` in [`aruco_detect.py`](../cube_minimal/cube_minimal/cube_pose/aruco_detect.py));
3. stima della posa dei singoli marker con IPPE (`estimate_marker_poses` in [`marker_pose.py`](../cube_minimal/cube_minimal/cube_pose/marker_pose.py));
4. ricostruzione della posa del cubo a partire da 1–3 facce (`estimate_cube_pose` in [`cube_pose.py`](../cube_minimal/cube_minimal/cube_pose/cube_pose.py));
5. generazione di strutture derivate (matrice di rotazione, quaternione, overlay diagnostico).

### Filtro marker e gestione outlier
Per stabilizzare l'uso dei marker nel tempo abbiamo introdotto il filtro opzionale [`MarkerFilter`](../cube_minimal/cube_minimal/cube_pose/filtering/marker_filter.py). Quando attivo (`active_marker_filter` nella configurazione), il filtro:
- scarta le detezioni sotto una soglia di area proiettata (`area_threshold_px`), utile per rimuovere marker troppo inclinati o parzialmente visibili;
- rileva inversioni spurie dell'asse Z tra frame consecutivi. Se `try_adj_marker` è `True`, eseguiamo un flip controllato della posa (`_flip_pose_z`) anziché scartare il marker;
- mantiene uno stato interno per ogni marker (`_MarkerState`) memorizzando quota Z e area per poter stabilire quando una misura è incoerente.
Il risultato del filtro (`MarkerFilterResult`) viene propagato alla pipeline PC così da tracciare marker scartati/corretti nel JSON finale.

### Calcolo della punta e orientazione
`PoseWorker` non si limita alla posa del cubo: la funzione `_compute_wand_tip` combina le normali delle facce associate a direzioni note (`wand_directions` in configurazione) e, applicando l'offset `wand_offset_m`, ricostruisce la posizione della punta rispetto al centro del cubo. La matrice di rotazione della punta viene derivata con `_compute_tip_rotation`, scegliendo un asse X coerente con il cubo e ortogonale alla direzione della bacchetta; da qui calcoliamo gli Euler ZYX, memorizzati sia in `euler_tip` sia nel vettore `tip_pose` (posizione + angoli) serializzato nel CSV.

### Strumenti di visualizzazione
Per l'analisi qualitativa e le presentazioni, `cube_minimal` offre funzioni di overlay in [`cube_pose/viz.py`](../cube_minimal/cube_minimal/cube_pose/viz.py):
- `draw_marker_outline` traccia il contorno delle facce rilevate;
- `draw_small_axes` visualizza gli assi locali del marker o del cubo;
- `draw_wirecube` proietta un reticolo del cubo nel piano immagine;
- `project_points_camframe` consente di verificare la proiezione di punti 3D nel frame camera.
Quando `estimate_cube_from_image` viene invocata con `return_overlay=True`, queste funzioni generano un'immagine annotata che il worker può salvare se `capture.save_frames` è attivo.

## Output dati e logging
Ogni sessione produce:
- cartella `session_*` con log di cattura (`session.log`) e, se richiesto, i frame originali e gli overlay;
- file JSON/CSV di posa nel percorso radice dell'app (`captures/` o directory configurata). Il formato CSV è pensato per integrazione con strumenti di robotica o analisi offline, mentre il JSON conserva tutti i dettagli (inclusi vettori `rvec`, `tvec`, numero di marker, info del filtro).
Il sistema registra inoltre log globali (`app.log` se `runtime.log_to_file` è `true`) e log per categoria (`POSE`, `SESSION`, `CAPTURE`) accessibili via console.

## Modalità operative e test
La configurazione [`config.yaml`](../pc/app/config.yaml) controlla frequenza di acquisizione, tipo di camera, dimensione delle code e attivazione del filtro marker. Possiamo eseguire:
- **Modalità simulata**: `capture.simulate_camera: true` e `capture.test_source_dir` puntato al dataset di esempio. Il backend [`TestCapture`](../pc/app/capture.py) riproduce le immagini sequenzialmente.
- **Modalità hardware**: `capture.simulate_camera: false`, backend [`OpenCvCapture`](../pc/app/capture.py) o [`PylonCapture`](../pc/app/capture.py) per camere Basler tramite `pypylon`.
- **Test unitari**: `pytest` nella cartella [`cube_minimal/tests`](../cube_minimal/tests) per validare funzioni di stima e filtri.

## Conclusione
Abbiamo costruito un ecosistema coerente in cui hardware, pipeline software e libreria algoritmica cooperano per fornire una stima di posa accurata e tracciabile della punta del pennino. La struttura modulare e la distinzione netta tra acquisizione, elaborazione e visualizzazione ci consentono di evolvere ciascun elemento (nuovi marker, nuovi algoritmi di smoothing, integrazione con robot) mantenendo stabilità operativa e tracciabilità dei dati. Questo documento rappresenta la base narrativa e tecnica per l'espansione verso una documentazione ufficiale completa.
