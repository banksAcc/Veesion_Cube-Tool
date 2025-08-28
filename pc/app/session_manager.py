import asyncio
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from capture import CameraCapture, TestCapture

FMT = "%Y-%m-%d_%H-%M-%S"  # leggibile e ordinabile

class Session:
    def __init__(self, root: Path, freq_ms: int, use_camera: bool, cfg: dict):
        self.root = root
        self.freq_ms = int(freq_ms)
        self.use_camera = use_camera
        self.cfg = cfg

        self.start_dt = datetime.now()
        self.end_dt: Optional[datetime] = None

        # dir iniziale "ongoing"
        self.dir = root / f"session_{self.start_dt.strftime(FMT)}__ongoing"
        self.dir.mkdir(parents=True, exist_ok=True)

        self.stop_evt = threading.Event()
        self.thread: Optional[threading.Thread] = None

        # per-Session log file (semplice): scrive nella stessa cartella
        self.session_log = self.dir / "session.log"
        self._log(
            f"[SESSION] start @ {self.start_dt.isoformat()} freq={self.freq_ms}ms simulate={not self.use_camera}"
        )

        # capture impl
        if self.use_camera:
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
        self.thread = threading.Thread(
            target=self.capturer.capture_loop,
            args=(self.dir, self.freq_ms, self.stop_evt, self._log),
            name=f"capture-{self.start_dt.strftime('%H%M%S')}",
            daemon=True
        )
        self.thread.start()

    def stop(self):
        self.end_dt = datetime.now()
        self._log(f"[SESSION] stop @ {self.end_dt.isoformat()}")
        self.stop_evt.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5.0)
        # rinomina cartella con start__end
        new_name = f"session_{self.start_dt.strftime(FMT)}__{self.end_dt.strftime(FMT)}"
        final_dir = self.root / new_name
        try:
            self.dir.rename(final_dir)
            self.dir = final_dir
        except Exception as e:
            self._log(f"[SESSION] rename failed: {e}")
        return self.dir, self.start_dt, self.end_dt

class SessionManager:
    def __init__(self, cfg: dict, output_root: Path, pose_queue: asyncio.Queue):
        self.cfg = cfg
        self.output_root = output_root
        self.pose_queue = pose_queue

        self.current: Optional[Session] = None
        self.lock = asyncio.Lock()

        self.debug = bool(cfg["runtime"].get("debug", True))
        self.keep_on_error = bool(cfg["capture"].get("keep_session_frames_on_error", True))

    async def handle_start_command(self):
        async with self.lock:
            if self.current is not None:
                print("[STATE] START ricevuto ma sessione già attiva -> IGNORO (duplicato)")
                return
            simulate = bool(self.cfg["capture"].get("simulate_camera", False))
            use_camera = not simulate
            freq_ms = int(self.cfg["capture"].get("frequency_ms", 200))
            self.current = Session(self.output_root, freq_ms, use_camera, self.cfg)
            self.current.start()
            print("[STATE] Sessione di scatto AVVIATA")

    async def handle_end_command(self):
        async with self.lock:
            if self.current is None:
                print("[STATE] END ricevuto ma nessuna sessione attiva -> IGNORO (duplicato)")
                return
            await self._stop_and_queue(self.current)
            self.current = None
            print("[STATE] Sessione di scatto FERMATA + messa in coda per posa")

    async def stop_session(self, reason: str = ""):
        async with self.lock:
            if self.current is None:
                return
            print(f"[STATE] Stop session (reason={reason})")
            await self._stop_and_queue(self.current)
            self.current = None

    async def _stop_and_queue(self, session: Session):
        try:
            final_dir, start_dt, end_dt = session.stop()
        except Exception as e:
            print(f"[SESSION] stop error: {e}")
            if not self.keep_on_error:
                print("[SESSION] WARNING: keep_on_error=False ma stop fallito: NON rimuovo nulla.")
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
        await self.stop_session(reason="shutdown")
