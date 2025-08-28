import asyncio
import sys
from bleak import BleakClient, BleakScanner

START_CMD = "START"
END_CMD   = "END"  # user ha confermato END

async def _discover_address(cfg: dict) -> str | None:
    addr = cfg["ble"].get("addr")
    if addr:
        return addr
    name_prefix = cfg["ble"].get("name_prefix", "ESP32-RGB-BLE")
    timeout = float(cfg["ble"].get("scan_timeout", 6.0))
    print(f"[BLE] Scansione {timeout:.1f}s per '{name_prefix}*' ...")
    devices = await BleakScanner.discover(timeout=timeout)
    for d in devices:
        if d.name and d.name.startswith(name_prefix):
            print(f"[BLE] Trovato: {d.name} @ {d.address}")
            return d.address
    print("[BLE] Nessun device trovato.")
    return None

async def run_ble_client(cfg: dict, session_mgr, out_queue: asyncio.Queue[str]):
    address = await _discover_address(cfg)
    if not address:
        print("[BLE] Nessun indirizzo: esco.")
        return

    # UUID NUS TX (notifiche dal device verso PC)
    NUS_TX_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
    # UUID NUS RX (messaggi dal PC verso device)
    NUS_RX_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"

    async def on_notify(_handle, data: bytearray):
        msg = data.decode(errors="ignore").strip().upper()
        if msg == START_CMD:
            await session_mgr.handle_start_command()
        elif msg == END_CMD or msg == "STOP":  # accettiamo anche "STOP"
            await session_mgr.handle_end_command()
        else:
            print(f"[BLE] Messaggio sconosciuto: {msg!r}")

    while True:
        try:
            print(f"[BLE] Connessione a {address} ...")
            async with BleakClient(address, timeout=10.0) as client:
                print(f"[BLE] Connesso: {client.is_connected}")
                if not client.is_connected:
                    raise RuntimeError("Connessione fallita")

                await client.start_notify(NUS_TX_UUID, on_notify)
                print("[BLE] Sottoscritto alle notifiche. (CTRL+C per uscire)")

                async def send_queued():
                    while True:
                        msg = await out_queue.get()
                        if msg is None:
                            break
                        try:
                            await client.write_gatt_char(NUS_RX_UUID, msg.encode())
                        except Exception as e:
                            print(f"[BLE] send error: {e}")

                sender_task = asyncio.create_task(send_queued())

                # Mantieni viva la connessione; se cade → stop capture se richiesto
                while client.is_connected:
                    await asyncio.sleep(0.5)

                sender_task.cancel()
                try:
                    await sender_task
                except asyncio.CancelledError:
                    pass

                print("[BLE] Disconnesso.")
                if cfg["capture"].get("stop_on_ble_disconnect", True):
                    await session_mgr.stop_session(reason="ble_disconnect")

        except KeyboardInterrupt:
            print("\n[BLE] Interrotto dall'utente.")
            return
        except Exception as e:
            print(f"[BLE] Errore: {e}")

        print("[BLE] Riprovo tra 2s ...")
        await asyncio.sleep(2.0)
