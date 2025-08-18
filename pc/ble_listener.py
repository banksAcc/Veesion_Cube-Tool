# ble_listener.py
# pip install bleak
import asyncio
import argparse
import sys
from bleak import BleakClient, BleakScanner

# Su Windows alcune versioni di Python/bleak preferiscono il WindowsSelectorEventLoop
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Nordic UART Service (NUS) - TX UUID: notifiche dal device verso PC
NUS_TX_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

async def find_device(name_prefix: str | None, address: str | None, scan_timeout: float = 6.0):
    if address:
        return address
    print(f"[SCAN] Scansione BLE per {scan_timeout:.1f}s...")
    devices = await BleakScanner.discover(timeout=scan_timeout)
    for d in devices:
        if name_prefix and d.name and d.name.startswith(name_prefix):
            print(f"[SCAN] Trovato: {d.name} @ {d.address}")
            return d.address
    print("[SCAN] Nessun device compatibile trovato.")
    return None

async def listen_notifications(address: str):
    async def on_notify(_handle, data: bytearray):
        msg = data.decode(errors="ignore").strip()
        print(f"[RX] {msg}")

    while True:
        try:
            print(f"[BLE] Connessione a {address} ...")
            async with BleakClient(address, timeout=10.0) as client:
                ok = client.is_connected
                print(f"[BLE] Connesso: {ok}")
                if not ok:
                    raise RuntimeError("Connessione fallita")

                await client.start_notify(NUS_TX_UUID, on_notify)
                print("[BLE] In ascolto notifiche su NUS/TX. (CTRL+C per uscire)")

                while client.is_connected:
                    await asyncio.sleep(1.0)

                print("[BLE] Disconnesso dal device.")

        except KeyboardInterrupt:
            print("\n[BLE] Interrotto dall’utente.")
            return
        except Exception as e:
            print(f"[BLE] Errore: {e}")

        print("[BLE] Riprovo tra 2 secondi...")
        await asyncio.sleep(2.0)

async def main():
    parser = argparse.ArgumentParser(description="Ascolta notifiche BLE dall'ESP32 (START/END).")
    parser.add_argument("--name", default="ESP32-RGB-BLE", help="Prefisso del nome del device (default: ESP32-RGB-BLE)")
    parser.add_argument("--addr", default=None, help="Indirizzo del device (MAC su Linux/Android, GUID su Windows)")
    parser.add_argument("--scan", type=float, default=6.0, help="Durata scansione in secondi (default: 6.0)")
    args = parser.parse_args()

    address = await find_device(args.name, args.addr, scan_timeout=args.scan)
    if not address:
        print("Suggerimenti:")
        print("- Premi a lungo il tasto BLE sull'ESP32 per entrare in advertising (LED blu 'breathing').")
        print("- Assicurati che il PC abbia il BLE attivo/supportato.")
        print("- Prova ad aumentare la durata di scansione con --scan 10")
        return

    await listen_notifications(address)

if __name__ == "__main__":
    asyncio.run(main())
