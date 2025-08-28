# test_basler.py
import asyncio, yaml
from pathlib import Path
from session_manager import SessionManager

cfg = yaml.safe_load(open("config.yaml"))
cfg["capture"]["simulate_camera"] = False
cfg["capture"]["camera_type"] = "pylon"   # serial/IP se necessario
output_root = Path(cfg["capture"]["output_root"])

async def main():
    sm = SessionManager(cfg, output_root, asyncio.Queue())
    await sm.handle_start_command()  # avvia acquisizione
    await asyncio.sleep(2)           # durata test (sec)
    await sm.handle_end_command()    # chiude sessione
    await sm.shutdown()

asyncio.run(main())
