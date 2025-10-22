"""Application entry point tying together BLE, capture and pose estimation."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Optional

import yaml

from ble_client import run_ble_client
from config_models import AppConfig
from logger import get_logger, setup_logging
from messages import BleMessage
from pose_worker import PoseWorker
from session_manager import SessionManager

# Loop policy recommended for Windows

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def load_config(path: Path) -> AppConfig:
    """Load a YAML configuration file into :class:`AppConfig`."""

    with path.open("r", encoding="utf-8") as f:
        data: Optional[dict] = yaml.safe_load(f)
    if not isinstance(data, dict):
        data = {}
    return AppConfig.from_mapping(data)


async def main() -> None:
    """Set up components and run the BLE client loop."""
    cfg = load_config(Path("config.yaml"))
    setup_logging(cfg)

    output_root = cfg.capture.output_root
    output_root.mkdir(parents=True, exist_ok=True)

    # Queue for outgoing BLE messages
    ble_queue: asyncio.Queue[Optional[BleMessage]] = asyncio.Queue()

    # Start async pose worker
    pose_worker = PoseWorker(cfg, output_root, ble_queue)
    await pose_worker.start()

    # Session manager with reference to the worker

    session_mgr = SessionManager(cfg, output_root, pose_worker.queue)

    # Start BLE client (blocking until interrupted)
    try:
        await run_ble_client(cfg, session_mgr, ble_queue)
    finally:
        # Clean shutdown
        await session_mgr.shutdown()
        await pose_worker.stop()


if __name__ == "__main__":
    main_log = get_logger("MAIN")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        main_log.info("Interrupted by user.")
