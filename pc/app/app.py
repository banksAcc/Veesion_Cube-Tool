import asyncio
import sys
import yaml
from pathlib import Path

from ble_client import run_ble_client
from pose_worker import PoseWorker
from session_manager import SessionManager

# Loop policy consigliata per Windows
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)

async def main():
    cfg = load_config(Path("config.yaml"))

    output_root = Path(cfg["capture"]["output_root"])
    output_root.mkdir(parents=True, exist_ok=True)

    # Avvia worker asincrono per la posa
    pose_worker = PoseWorker(cfg, output_root)
    await pose_worker.start()

    # Gestore sessioni (scatti) con riferimento al worker
    session_mgr = SessionManager(cfg, output_root, pose_worker.queue)

    # Avvia BLE client (blocking finché non interrompi)
    try:
        await run_ble_client(cfg, session_mgr)
    finally:
        # Chiusura pulita
        await session_mgr.shutdown()
        await pose_worker.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[MAIN] Interrotto dall'utente.")
