"""Manage capture sessions and coordinate start/stop commands."""

import asyncio
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from capture import CameraCapture, TestCapture

FMT = "%Y-%m-%d_%H-%M-%S"  # readable and sortable

class Session:
    """Represent a single capture session."""

    def __init__(self, root: Path, freq_ms: int, use_camera: bool, cfg: dict):
        """Create a new session and prepare the capture directory.

        Args:
            root (Path): Root directory where sessions are stored.
            freq_ms (int): Capture frequency in milliseconds.
            use_camera (bool): Whether to capture from a camera or test images.
            cfg (dict): Application configuration.
        """

        self.root = root
        self.freq_ms = int(freq_ms)
        self.use_camera = use_camera
        self.cfg = cfg

        self.start_dt = datetime.now()
        self.end_dt: Optional[datetime] = None

        # initial "ongoing" directory
        self.dir = root / f"session_{self.start_dt.strftime(FMT)}__ongoing"
        self.dir.mkdir(parents=True, exist_ok=True)

        self.stop_evt = threading.Event()
        self.thread: Optional[threading.Thread] = None

        # per-session log file stored in the same folder
        self.session_log = self.dir / "session.log"
        self._log(
            f"[SESSION] start @ {self.start_dt.isoformat()} freq={self.freq_ms}ms use_camera={self.use_camera}"
        )

        # capture implementation
        if self.use_camera:
            self.capturer = CameraCapture(self.cfg)
        else:
            self.capturer = TestCapture(self.cfg)

    def _log(self, msg: str):
        """Print and append a message to the session log."""

        print(msg)
        try:
            with self.session_log.open("a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except Exception:
            pass

    def start(self):
        """Start the capture loop in a background thread."""

        self.thread = threading.Thread(
            target=self.capturer.capture_loop,
            args=(self.dir, self.freq_ms, self.stop_evt, self._log),
            name=f"capture-{self.start_dt.strftime('%H%M%S')}",
            daemon=True,
        )
        self.thread.start()

    def stop(self):
        """Stop capture and finalize the session directory.

        Returns:
            tuple[Path, datetime, datetime]: Final directory and start/end times.
        """

        self.end_dt = datetime.now()
        self._log(f"[SESSION] stop @ {self.end_dt.isoformat()}")
        self.stop_evt.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5.0)
        # rename directory with start__end
        new_name = f"session_{self.start_dt.strftime(FMT)}__{self.end_dt.strftime(FMT)}"
        final_dir = self.root / new_name
        try:
            self.dir.rename(final_dir)
            self.dir = final_dir
        except Exception as e:
            self._log(f"[SESSION] rename failed: {e}")
        return self.dir, self.start_dt, self.end_dt

class SessionManager:
    """Manage session lifecycle and forward jobs to the pose worker."""

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
        self.keep_on_error = bool(cfg["capture"].get("keep_session_frames_on_error", True))

    async def handle_start_command(self):
        """Begin a new capture session if none is active.

        Side Effects:
            Creates a :class:`Session`, starts its capture thread and prints
            status messages.
        """

        async with self.lock:
            if self.current is not None:
                print(
                    "[STATE] START received but session already active -> IGNORE (duplicate)"
                )
                return
            use_camera = bool(self.cfg["capture"].get("use_camera", True))
            freq_ms = int(self.cfg["capture"].get("frequency_ms", 200))
            self.current = Session(self.output_root, freq_ms, use_camera, self.cfg)
            self.current.start()
            print("[STATE] Capture session STARTED")

    async def handle_end_command(self):
        """End the current session if one is running.

        Side Effects:
            Stops the active :class:`Session`, queues it for pose estimation and
            prints status messages.
        """

        async with self.lock:
            if self.current is None:
                print(
                    "[STATE] END received but no active session -> IGNORE (duplicate)"
                )
                return
            await self._stop_and_queue(self.current)
            self.current = None
            print("[STATE] Capture session STOPPED and queued for pose")

    async def stop_session(self, reason: str = ""):
        """Force-stop the current session and queue it for processing.

        Args:
            reason (str): Text describing why the session is being stopped.

        Side Effects:
            Stops the session, enqueues it for pose estimation and prints
            status messages.
        """

        async with self.lock:
            if self.current is None:
                return
            print(f"[STATE] Stop session (reason={reason})")
            await self._stop_and_queue(self.current)
            self.current = None

    async def _stop_and_queue(self, session: Session):
        """Stop a session and enqueue it for pose estimation.

        Args:
            session (Session): Session instance to be stopped.

        Side Effects:
            May remove captured frames and always enqueues a job for the pose
            worker if enabled.
        """

        try:
            final_dir, start_dt, end_dt = session.stop()
        except Exception as e:
            print(f"[SESSION] stop error: {e}")
            if not self.keep_on_error:
                print(
                    "[SESSION] WARNING: keep_on_error=False but stop failed: NOT removing anything."
                )
            return

        # enqueue job for pose
        if bool(self.cfg["pose"].get("enabled", True)):
            job = {
                "session_dir": str(final_dir),
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat(),
                "freq_ms": session.freq_ms,
            }
            await self.pose_queue.put(job)

    async def shutdown(self):
        """Stop any active session as part of application shutdown.

        Side Effects:
            Stops an ongoing session and prints status messages.
        """

        await self.stop_session(reason="shutdown")
