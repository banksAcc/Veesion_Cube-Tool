"""Session orchestration and capture strategy selection.

This module exposes :class:`SessionManager`, which reacts to BLE commands and
starts or stops capture sessions. Each :class:`Session` chooses a concrete
capture backend according to ``cfg['capture']['use_camera']``:

* ``True`` -> :class:`OpenCvCapture` reads frames from a physical camera (webcam
  or Basler via ``pypylon`` when integrated).
* ``False`` -> :class:`TestCapture` replays static images from
  ``test_source_dir`` for deterministic runs.

The flag is typically set in ``pc/app/config.yaml`` and allows developers to
switch between real hardware and test data without code changes.
"""

import asyncio
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from capture import BaseCapture, OpenCvCapture, PylonCapture, TestCapture
from logger import get_logger

FMT = "%Y-%m-%d_%H-%M-%S"  # readable and sortable

session_logger = get_logger("SESSION")
state_logger = get_logger("STATE")
capture_logger = get_logger("CAPTURE")


class Session:
    """Represent a single capture session on disk."""

    def __init__(
        self,
        root: Path,
        freq_ms: int,
        use_camera: bool,
        cfg: dict,
        capturer: BaseCapture,
        auto_close: bool,
    ):
        """Create a new session and prepare the capture directory.

        Args:
            root (Path): Root directory where sessions are stored.
            freq_ms (int): Capture frequency in milliseconds.
            use_camera (bool): Whether to capture from a camera or test images.
            cfg (dict): Application configuration.
            capturer (BaseCapture): Backend instance that performs acquisition.
            auto_close (bool): Whether the backend should auto-close at loop end.
        """

        if capturer is None:
            raise ValueError("capturer is required")

        self.root = root
        self.freq_ms = int(freq_ms)
        self.use_camera = use_camera
        self.cfg = cfg
        self.capturer = capturer
        self.auto_close = bool(auto_close)

        self.start_dt = datetime.now()
        self.end_dt: Optional[datetime] = None

        # initial directory "ongoing"
        self.dir = root / f"session_{self.start_dt.strftime(FMT)}__ongoing"
        self.dir.mkdir(parents=True, exist_ok=True)

        self.stop_evt = threading.Event()
        self.thread: Optional[threading.Thread] = None

        # simple per-session log file stored in the same folder
        self.session_log = self.dir / "session.log"
        self._log(
            f"start @ {self.start_dt.isoformat()} freq={self.freq_ms}ms use_camera={self.use_camera}"
        )

    def _log(self, msg: str, level: str = "info"):
        getattr(session_logger, level)(msg)
        try:
            with self.session_log.open("a", encoding="utf-8") as f:
                f.write(f"[SESSION] {msg}\n")
        except Exception:
            pass

    def log_capture(self, msg: str, level: str = "info"):
        getattr(capture_logger, level)(msg)
        try:
            with self.session_log.open("a", encoding="utf-8") as f:
                f.write(f"[CAPTURE] {msg}\n")
        except Exception:
            pass

    def start(self):
        """Spawn the capture thread."""
        self.capturer.set_auto_close(self.auto_close)
        self.thread = threading.Thread(
            target=self.capturer.capture_loop,
            args=(self.dir, self.freq_ms, self.stop_evt, self.log_capture),
            name=f"capture-{self.start_dt.strftime('%H%M%S')}",
            daemon=True,
        )
        self.thread.start()

    def stop(self):
        """Stop capture and rename directory with start and end timestamps."""
        self.end_dt = datetime.now()
        self._log(f"stop @ {self.end_dt.isoformat()}")
        self.stop_evt.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5.0)
        # rename folder with start__end
        new_name = f"session_{self.start_dt.strftime(FMT)}__{self.end_dt.strftime(FMT)}"
        final_dir = self.root / new_name
        try:
            self.dir.rename(final_dir)
            self.dir = final_dir
        except Exception as e:
            self._log(f"rename failed: {e}", level="error")
        return self.dir, self.start_dt, self.end_dt


class SessionManager:
    """Manage capture sessions and queue them for pose estimation."""

    def __init__(self, cfg: dict, output_root: Path, pose_queue: asyncio.Queue):
        """Initialize the manager with configuration and queues.

        Args:
            cfg (dict): Application configuration.
            output_root (Path): Directory where session data are stored.
            pose_queue (asyncio.Queue): Queue for enqueuing pose jobs.
        """

        self.cfg = cfg
        self.output_root = output_root
        self.pose_queue = pose_queue

        self.current: Optional[Session] = None
        self.lock = asyncio.Lock()

        self.debug = bool(cfg["runtime"].get("debug", True))
        self.keep_on_error = bool(
            cfg["capture"].get("keep_session_frames_on_error", True)
        )

        self.simulate = bool(cfg["capture"].get("simulate_camera", False))
        self.use_camera = not self.simulate
        self.keep_camera_warm = bool(cfg["capture"].get("keep_camera_warm", True))
        self.capturer: Optional[BaseCapture] = None

    def _capture_log(self, msg: str, level: str = "info") -> None:
        getattr(capture_logger, level)(msg)

    def _create_camera_capturer(self) -> BaseCapture:
        cam_type = str(self.cfg["capture"].get("camera_type", "opencv")).lower()
        if cam_type == "pylon":
            return PylonCapture(self.cfg)
        return OpenCvCapture(self.cfg)

    def _ensure_camera_capturer(self) -> BaseCapture:
        if self.capturer is None:
            self.capturer = self._create_camera_capturer()
        return self.capturer

    def _release_capturer(self) -> None:
        if self.capturer is None:
            return
        try:
            self.capturer.close(self._capture_log)
        except Exception as exc:  # pragma: no cover - hardware dependent
            capture_logger.error(f"Capture close error: {exc}")
        finally:
            self.capturer = None

    async def handle_start_command(self):
        """Handle START messages from BLE by creating a new session."""
        async with self.lock:
            if self.current is not None:
                state_logger.warning(
                    "START received but session already active -> IGNORE (duplicate)"
                )
                return

            freq_ms = int(self.cfg["capture"].get("frequency_ms", 200))

            if self.use_camera:
                capturer = self._ensure_camera_capturer()
                auto_close = not (self.keep_camera_warm and self.use_camera)
            else:
                capturer = TestCapture(self.cfg)
                auto_close = True

            session = Session(
                self.output_root,
                freq_ms,
                self.use_camera,
                self.cfg,
                capturer,
                auto_close,
            )
            self.current = session
            session.start()
            state_logger.info("Capture session STARTED")

            if bool(self.cfg["pose"].get("enabled", True)):
                pose_job = {
                    "action": "start",
                    "session_key": session.start_dt.isoformat(),
                    "session_dir": str(session.dir),
                    "start": session.start_dt.isoformat(),
                    "freq_ms": session.freq_ms,
                }
                await self.pose_queue.put(pose_job)

    async def handle_end_command(self):
        """Handle END messages by closing the current session."""
        async with self.lock:
            if self.current is None:
                state_logger.warning(
                    "END received but no active session -> IGNORE (duplicate)"
                )
                return
            await self._stop_and_queue(self.current)
            self.current = None
            state_logger.info("Capture session STOPPED and queued for pose")

    async def stop_session(self, reason: str = ""):
        """Force stop of the active session, providing a reason."""
        async with self.lock:
            if self.current is None:
                return
            state_logger.info(f"Stop session (reason={reason})")
            await self._stop_and_queue(self.current)
            self.current = None

    async def on_ble_connected(self):
        """Warm up the camera as soon as the BLE device connects."""
        if not (self.use_camera and self.keep_camera_warm):
            return
        async with self.lock:
            capturer = self._ensure_camera_capturer()
            capturer.set_auto_close(False)
            try:
                capturer.open(self._capture_log)
            except Exception as exc:  # pragma: no cover - hardware dependent
                capture_logger.error(f"Capture warm-up failed: {exc}")

    async def on_ble_disconnected(self):
        """Stop session and release the camera after BLE disconnects."""
        async with self.lock:
            if self.current is not None:
                await self._stop_and_queue(self.current)
                self.current = None
                state_logger.info("Capture session STOPPED due to BLE disconnect")
            self._release_capturer()

    async def _stop_and_queue(self, session: Session):
        """Stop the session and enqueue it for pose estimation."""
        try:
            final_dir, start_dt, end_dt = session.stop()
        except Exception as e:
            session_logger.error(f"stop error: {e}")
            if not self.keep_on_error:
                session_logger.warning(
                    "keep_on_error=False but stop failed: NOT removing anything."
                )
            return

        if bool(self.cfg["pose"].get("enabled", True)):
            pose_job = {
                "action": "end",
                "session_key": start_dt.isoformat(),
                "session_dir": str(final_dir),
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat(),
                "freq_ms": session.freq_ms,
            }
            await self.pose_queue.put(pose_job)

    async def shutdown(self):
        """Stop current session when shutting down."""
        await self.stop_session(reason="shutdown")
        async with self.lock:
            self._release_capturer()

