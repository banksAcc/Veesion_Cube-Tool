"""Entry point for the PC application.

This module loads configuration, sets up the pose worker and session manager,
and starts the BLE client used to trigger image capture sessions.
"""

import asyncio
import sys
from pathlib import Path

import yaml

from ble_client import run_ble_client
from pose_worker import PoseWorker
from session_manager import SessionManager

# Recommended event loop policy for Windows
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def load_config(path: Path) -> dict:
    """Read a YAML configuration file.

    Args:
        path (Path): Path to the configuration file.

    Returns:
        dict: Parsed configuration content.

    Side Effects:
        Reads from disk.
    """

    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


async def main():
    """Run the main application coroutine.

    Loads configuration, creates background workers and starts the BLE client.
    The coroutine exits only when the BLE client stops and performs a clean
    shutdown of resources.

    Returns:
        None

    Side Effects:
        Creates output directories, starts asynchronous tasks and interacts
        with the BLE device.
    """

    cfg = load_config(Path("config.yaml"))

    output_root = Path(cfg["capture"]["output_root"])
    output_root.mkdir(parents=True, exist_ok=True)

    # Queue for outgoing BLE messages
    ble_queue: asyncio.Queue[str] = asyncio.Queue()

    # Start asynchronous pose worker
    pose_worker = PoseWorker(cfg, output_root, ble_queue)
    await pose_worker.start()

    # Session manager for captures referencing the worker
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
