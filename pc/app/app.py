"""Application entry point tying together BLE, capture and pose estimation."""

import asyncio
import sys
import yaml
from pathlib import Path

from ble_client import run_ble_client
from pose_worker import PoseWorker
from session_manager import SessionManager

# Recommended event loop policy for Windows
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def load_config(path: Path) -> dict:
    """Load a YAML configuration file and return it as a dictionary."""
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


async def main():
    """Set up components and run the BLE client loop."""
    cfg = load_config(Path("config.yaml"))

    output_root = Path(cfg["capture"]["output_root"])
    output_root.mkdir(parents=True, exist_ok=True)

    # Queue for outgoing BLE messages
    ble_queue: asyncio.Queue[str] = asyncio.Queue()

    # Start asynchronous worker for pose estimation
    pose_worker = PoseWorker(cfg, output_root, ble_queue)
    await pose_worker.start()

    # Session manager (captures) with reference to the worker
    session_mgr = SessionManager(cfg, output_root, pose_worker.queue)

    # Start BLE client (blocking until interrupted)
    try:
        await run_ble_client(cfg, session_mgr, ble_queue)
    finally:
        # Clean shutdown
        await session_mgr.shutdown()
        await pose_worker.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[MAIN] Interrupted by user.")
