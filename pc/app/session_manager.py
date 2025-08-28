import asyncio
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from capture import CameraCapture, TestCapture, PylonCapture

FMT = "%Y-%m-%d_%H-%M-%S"  # readable and sortable


class Session:
    """Represent a single capture session on disk."""

    def __init__(self, root: Path, freq_ms: int, use_camera: bool, cfg: dict):
        self.root = root
        self.freq_ms = int(freq_ms)
        self.use_camera = use_camera
        self.cfg = cfg

        self.start_dt = datetime.now()
        self.end_dt: Optional[datetime] = None

        # initial directory marked as ongoing
        self.dir = root / f"session_{self.start_dt.strftime(FMT)}__ongoing"
        self.dir.mkdir(parents=True, exist_ok=True)

        self.stop_evt = threading.Event()
        self.thread: Optional[threading.Thread] = None

        # per-session log file in the session directory
        self.session_log = self.dir / "session.log"
        self._log(
            f"[SESSION] start @ {self.start_dt.isoformat()} freq={self.freq_ms}ms use_camera={self.use_camera}"
        )

        # capture implementation
        if self.use_camera:
            cam_type = str(self.cfg["capture"].get("camera_type", "opencv")).lower()
            if cam_type == "pylon":
                self.capturer = PylonCapture(self.cfg)
            else:
                self.capturer = CameraCapture(self.cfg)
        else:
            self.capturer = TestCapture(self.cfg)

    def _log(self, msg: str):
        print(msg)
        try:
            with self.session_log.open("a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except Exception:
            pass

    def start(self):
        """Spawn the capture thread."""
        self.thread = threading.Thread(
            target=self.capturer.capture_loop,
            args=(self.dir, self.freq_ms, self.stop_evt, self._log),
            name=f"capture-{self.start_dt.strftime('%H%M%S')}",
            daemon=True,
        )
        self.thread.start()

    def stop(self):
        """Stop capture and rename directory with start and end timestamps."""
        self.end_dt = datetime.now()
        self._log(f"[SESSION] stop @ {self.end_dt.isoformat()}")
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
            self._log(f"[SESSION] rename failed: {e}")
        return self.dir, self.start_dt, self.end_dt


class SessionManager:
    """Manage capture sessions and queue them for pose estimation."""

    def __init__(self, cfg: dict, output_root: Path, pose_queue: asyncio.Queue):
        self.cfg = cfg
        self.output_root = output_root
        self.pose_queue = pose_queue

        self.current: Optional[Session] = None
        self.lock = asyncio.Lock()

        self.debug = bool(cfg["runtime"].get("debug", True))
        self.keep_on_error = bool(cfg["capture"].get("keep_session_frames_on_error", True))

    async def handle_start_command(self):
        """Handle START messages from BLE by creating a new session."""
        async with self.lock:
            if self.current is not None:
                print("[STATE] START received but session already active -> IGNORE (duplicate)")
                return
            use_camera = bool(self.cfg["capture"].get("use_camera", True))
            freq_ms = int(self.cfg["capture"].get("frequency_ms", 200))
            self.current = Session(self.output_root, freq_ms, use_camera, self.cfg)
            self.current.start()
            print("[STATE] Capture session STARTED")

    async def handle_end_command(self):
        """Handle END messages by closing the current session."""
        async with self.lock:
            if self.current is None:
                print("[STATE] END received but no active session -> IGNORE (duplicate)")
                return
            await self._stop_and_queue(self.current)
            self.current = None
            print("[STATE] Capture session STOPPED and queued for pose")

    async def stop_session(self, reason: str = ""):
        """Force stop of the active session, providing a reason."""
        async with self.lock:
            if self.current is None:
                return
            print(f"[STATE] Stop session (reason={reason})")
            await self._stop_and_queue(self.current)
            self.current = None

    async def _stop_and_queue(self, session: Session):
        """Stop the session and enqueue it for pose estimation."""
        try:
            final_dir, start_dt, end_dt = session.stop()
        except Exception as e:
            print(f"[SESSION] stop error: {e}")
            if not self.keep_on_error:
                print("[SESSION] WARNING: keep_on_error=False but stop failed: NOT removing anything.")
            return

        # enqueue job for pose estimation
        if bool(self.cfg["pose"].get("enabled", True)):
            job = {
                "session_dir": str(final_dir),
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat(),
                "freq_ms": session.freq_ms,
            }
            await self.pose_queue.put(job)

    async def shutdown(self):
        """Stop current session when shutting down."""
        await self.stop_session(reason="shutdown")
