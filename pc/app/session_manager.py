"""Session orchestration and capture strategy selection.

This module exposes :class:`SessionManager`, which reacts to BLE commands and
starts or stops capture sessions. Each :class:`Session` chooses a concrete
capture backend according to ``cfg.capture.simulate_camera``:

* ``True`` -> :class:`TestCapture` replays static images from
  ``test_source_dir`` for deterministic runs.
* ``False`` -> :class:`OpenCvCapture` reads frames from a physical camera
  or Basler via ``pypylon`` when integrated.

The flag is typically set in ``pc/app/config.yaml`` and allows developers to
switch between real hardware and test data without code changes.
"""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from concurrent.futures import TimeoutError

from capture import BaseCapture, OpenCvCapture, PylonCapture, TestCapture
from config_models import AppConfig
from logger import get_logger
from messages import PoseEndMessage, PoseStartMessage, PoseWorkerPayload
from stream import FramePacket

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
        capturer: BaseCapture,
        auto_close: bool,
        loop: asyncio.AbstractEventLoop,
        frame_queue: asyncio.Queue[Optional[FramePacket]],
        save_frames: bool,
    ):
        """Create a new session and prepare the capture directory.

        Args:
            root (Path): Root directory where sessions are stored.
            freq_ms (int): Capture frequency in milliseconds.
            use_camera (bool): Whether to capture from a camera or test images.
            capturer (BaseCapture): Backend instance that performs acquisition.
            auto_close (bool): Whether the backend should auto-close at loop end.
        """

        if capturer is None:
            raise ValueError("capturer is required")

        self.root = root
        self.freq_ms = int(freq_ms)
        self.use_camera = use_camera
        self.capturer = capturer
        self.auto_close = bool(auto_close)
        self.loop = loop
        self.frame_queue = frame_queue
        self.save_frames = bool(save_frames)

        self.start_dt = datetime.now()
        self.end_dt: Optional[datetime] = None

        self.dir = root / f"session_{self.start_dt.strftime(FMT)}"
        self.dir.mkdir(parents=True, exist_ok=True)

        self.stop_evt = threading.Event()
        self.thread: Optional[threading.Thread] = None

        # simple per-session log file stored in the same folder
        self.session_log = self.dir / "session.log"
        self._log(
            f"start @ {self.start_dt.isoformat()} freq={self.freq_ms}ms use_camera={self.use_camera}"
        )

    def _log(self, msg: str, level: str = "info") -> None:
        getattr(session_logger, level)(msg)
        try:
            with self.session_log.open("a", encoding="utf-8") as f:
                f.write(f"[SESSION] {msg}\n")
        except Exception:
            pass

    def log_capture(self, msg: str, level: str = "info") -> None:
        getattr(capture_logger, level)(msg)
        try:
            with self.session_log.open("a", encoding="utf-8") as f:
                f.write(f"[CAPTURE] {msg}\n")
        except Exception:
            pass

    def start(self) -> None:
        """Spawn the capture thread."""
        self.capturer.set_auto_close(self.auto_close)
        self.thread = threading.Thread(
            target=self.capturer.capture_loop,
            args=(
                self.dir,
                self.freq_ms,
                self.stop_evt,
                self.log_capture,
                self._handle_frame,
            ),
            name=f"capture-{self.start_dt.strftime('%H%M%S')}",
            daemon=True,
        )
        self.thread.start()

    def stop(self) -> tuple[Path, datetime, Optional[datetime]]:
        """Stop capture and signal the end of the frame stream."""
        self.end_dt = datetime.now()
        self._log(f"stop @ {self.end_dt.isoformat()}")
        self.stop_evt.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5.0)
        self._signal_stream_closed()
        return self.dir, self.start_dt, self.end_dt

    def _handle_frame(self, frame: Any, filename: str, captured_at: float, index: int) -> None:
        packet = FramePacket(
            session_key=self.start_dt.isoformat(),
            index=index,
            timestamp=captured_at,
            frame=frame,
            filename=filename,
            save_path=(self.dir / filename) if self.save_frames else None,
        )
        fut = asyncio.run_coroutine_threadsafe(self.frame_queue.put(packet), self.loop)
        try:
            fut.result(timeout=5.0)
        except TimeoutError:
            self.log_capture("Timed out while queueing frame", "warning")
        except Exception as exc:  # pragma: no cover - unexpected threading issue
            self.log_capture(f"Failed to queue frame: {exc}", "error")

    def _signal_stream_closed(self) -> None:
        try:
            fut = asyncio.run_coroutine_threadsafe(
                self.frame_queue.put(None), self.loop
            )
            fut.result(timeout=5.0)
        except TimeoutError:
            self.log_capture("Timed out closing frame queue", "warning")
        except Exception:
            pass


class SessionManager:
    """Manage capture sessions and queue them for pose estimation."""

    def __init__(
        self,
        cfg: AppConfig,
        output_root: Path,
        pose_queue: asyncio.Queue[Optional[PoseWorkerPayload]],
    ):
        """Initialize the manager with configuration and queues."""

        self.cfg = cfg
        self.raw_cfg = cfg.as_dict()
        self.output_root = output_root
        self.pose_queue = pose_queue

        self.current: Optional[Session] = None
        self.lock = asyncio.Lock()

        self.debug = bool(cfg.runtime.debug)

        self.simulate = bool(cfg.capture.simulate_camera)
        self.use_camera = not self.simulate
        self.keep_camera_warm = bool(cfg.capture.keep_camera_warm)
        self.save_frames = bool(cfg.capture.save_frames)
        self.frame_queue_size = int(cfg.capture.frame_queue_size)
        self.capturer: Optional[BaseCapture] = None

    def _capture_log(self, msg: str, level: str = "info") -> None:
        getattr(capture_logger, level)(msg)

    def _create_camera_capturer(self) -> BaseCapture:
        cam_type = str(self.cfg.capture.camera_type).lower()
        if cam_type == "pylon":
            return PylonCapture(self.raw_cfg)
        return OpenCvCapture(self.raw_cfg)

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

    async def handle_start_command(self) -> None:
        """Handle START messages from BLE by creating a new session."""
        async with self.lock:
            if self.current is not None:
                state_logger.warning(
                    "START received but session already active -> IGNORE (duplicate)"
                )
                return

            freq_ms = int(self.cfg.capture.frequency_ms)

            if self.use_camera:
                capturer = self._ensure_camera_capturer()
                auto_close = not (self.keep_camera_warm and self.use_camera)
            else:
                capturer = TestCapture(self.raw_cfg)
                auto_close = True

            loop = asyncio.get_running_loop()
            frame_queue: asyncio.Queue[Optional[FramePacket]] = asyncio.Queue(
                maxsize=self.frame_queue_size
            )
            session = Session(
                self.output_root,
                freq_ms,
                self.use_camera,
                capturer,
                auto_close,
                loop,
                frame_queue,
                self.save_frames,
            )
            self.current = session
            session.start()
            state_logger.info("Capture session STARTED")

            if self.cfg.pose.enabled:
                pose_job = PoseStartMessage(
                    session_key=session.start_dt.isoformat(),
                    session_dir=session.dir,
                    frame_queue=frame_queue,
                    start=session.start_dt.isoformat(),
                    freq_ms=session.freq_ms,
                    label=session.dir.name,
                    save_frames=session.save_frames,
                    save_dir=session.dir if session.save_frames else None,
                )
                await self.pose_queue.put(pose_job)

    async def handle_end_command(self) -> None:
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

    async def stop_session(self, reason: str = "") -> None:
        """Force stop of the active session, providing a reason."""
        async with self.lock:
            if self.current is None:
                return
            state_logger.info(f"Stop session (reason={reason})")
            await self._stop_and_queue(self.current)
            self.current = None

    async def on_ble_connected(self) -> None:
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

    async def on_ble_disconnected(self) -> None:
        """Stop session and release the camera after BLE disconnects."""
        async with self.lock:
            if self.current is not None:
                await self._stop_and_queue(self.current)
                self.current = None
                state_logger.info("Capture session STOPPED due to BLE disconnect")
            self._release_capturer()

    async def _stop_and_queue(self, session: Session) -> None:
        """Stop the session and enqueue it for pose estimation."""
        try:
            final_dir, start_dt, end_dt = session.stop()
        except Exception as e:
            session_logger.error(f"stop error: {e}")
            return

        if self.cfg.pose.enabled:
            pose_job = PoseEndMessage(
                session_key=start_dt.isoformat(),
                session_dir=final_dir,
                start=start_dt.isoformat(),
                end=end_dt.isoformat() if end_dt else start_dt.isoformat(),
                freq_ms=session.freq_ms,
                label=final_dir.name,
                save_dir=final_dir if session.save_frames else None,
            )
            await self.pose_queue.put(pose_job)

    async def shutdown(self) -> None:
        """Stop current session when shutting down."""
        await self.stop_session(reason="shutdown")
        async with self.lock:
            self._release_capturer()

