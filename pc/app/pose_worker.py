"""Asynchronous worker that computes pose from captured frames."""

import asyncio
import json
import shutil
import time
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple

from cube_minimal.cube_pose.api import estimate_cube_from_image

from logger import get_logger

try:
    import cv2
    import numpy as np
    HAS_CV = True
except Exception:
    cv2, np, HAS_CV = None, None, False

log = get_logger("POSE")

FRAME_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}


@dataclass
class SessionJob:
    """Track state for an in-flight pose estimation session."""

    key: str
    current_dir: Path
    freq_ms: int
    start_iso: str
    results: dict
    processed: set[str] = field(default_factory=set)
    final_dir: Optional[Path] = None
    end_iso: Optional[str] = None
    finished: threading.Event = field(default_factory=threading.Event)
    task: Optional[asyncio.Task] = None
    overlay_window: Optional[str] = None


class PoseWorker:
    """Asynchronous worker that estimates cube pose for capture sessions."""

    def __init__(self, cfg: dict, output_root: Path, ble_queue: asyncio.Queue[str]):
        self.cfg = cfg
        self.output_root = output_root
        self.queue: asyncio.Queue = asyncio.Queue()
        self.tasks: list[asyncio.Task] = []
        self.max_jobs = int(cfg["pose"].get("max_parallel_jobs", 1))
        self.enabled = bool(cfg["pose"].get("enabled", True))
        self.ble_queue = ble_queue
        try:
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            self.loop = asyncio.get_event_loop()

        self.sessions: Dict[str, SessionJob] = {}
        self.method = cfg["pose"].get("method", "cube").lower()
        self.delete_frames = bool(cfg["pose"].get("delete_frames_after_processing", True))
        self.debug = bool(cfg["runtime"].get("debug", True))
        self.show_overlay = bool(cfg["pose"].get("show_overlay_window", False)) and HAS_CV
        self.overlay_title = cfg["pose"].get("overlay_window_name", "Pose Overlay")
        self.idle_checks = int(cfg["pose"].get("stream_idle_checks", 3))
        self.poll_floor = float(cfg["pose"].get("stream_poll_interval_ms", 100)) / 1000.0
        self.pose_cfg = cfg["pose"].get("cube", {})

    async def start(self):
        """Spawn worker tasks if pose estimation is enabled."""
        if not self.enabled:
            log.info("disabled")
            return
        log.info(f"starting workers = {self.max_jobs}")
        for _ in range(self.max_jobs):
            self.tasks.append(asyncio.create_task(self._worker()))

    async def stop(self):
        """Signal workers to exit and wait for completion."""
        for job in list(self.sessions.values()):
            job.finished.set()
        for _ in self.tasks:
            await self.queue.put(None)
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()
        await asyncio.gather(
            *(job.task for job in list(self.sessions.values()) if job.task),
            return_exceptions=True,
        )
        self.sessions.clear()

    async def _worker(self):
        """Consume jobs from the queue and dispatch session handling."""
        while True:
            job = await self.queue.get()
            if job is None:
                break
            action = job.get("action")
            if action == "start":
                self._handle_start(job)
            elif action == "end":
                self._handle_end(job)
            else:
                log.warning(f"Unknown pose job action: {action}")

    def _handle_start(self, payload: dict) -> None:
        session_key = payload["session_key"]
        if session_key in self.sessions:
            log.warning(f"Session {session_key} already tracked -> ignoring start")
            return

        session_dir = Path(payload["session_dir"])
        freq_ms = int(payload["freq_ms"])
        results = {
            "session": session_dir.name,
            "start": payload["start"],
            "end": None,
            "frequency_ms": freq_ms,
            "method": self.method,
            "frames": [],
        }
        job = SessionJob(
            key=session_key,
            current_dir=session_dir,
            freq_ms=freq_ms,
            start_iso=payload["start"],
            results=results,
        )
        job.task = asyncio.create_task(self._run_session(job))
        self.sessions[session_key] = job
        log.info(f"Pose session started for {session_dir.name}")

    def _handle_end(self, payload: dict) -> None:
        session_key = payload["session_key"]
        job = self.sessions.get(session_key)
        if job is None:
            log.warning(f"Pose END for unknown session {session_key}")
            return
        job.final_dir = Path(payload["session_dir"])
        job.end_iso = payload.get("end")
        job.results["end"] = job.end_iso
        job.finished.set()
        log.info(f"Pose session finishing for {job.final_dir.name}")

    async def _run_session(self, job: SessionJob):
        try:
            await asyncio.to_thread(self._process_session_stream, job)
        finally:
            self.sessions.pop(job.key, None)

    def _process_session_stream(self, job: SessionJob) -> None:
        poll_interval = max(self.poll_floor, job.freq_ms / 1000.0 / 2.0)
        idle_rounds = 0
        active_dir = job.current_dir
        self._notify_ble("COMPUTATION START")
        try:
            while True:
                target_dir = job.final_dir if job.final_dir and job.final_dir.exists() else active_dir
                try:
                    frames = sorted(
                        p for p in target_dir.glob("*") if p.suffix.lower() in FRAME_EXTS
                    )
                except FileNotFoundError:
                    time.sleep(poll_interval)
                    continue

                new_frames = [p for p in frames if p.name not in job.processed]
                if new_frames:
                    idle_rounds = 0
                    for frame_path in new_frames:
                        frame_result, overlay = self._process_frame(frame_path)
                        job.results["frames"].append(frame_result)
                        job.processed.add(frame_path.name)
                        if overlay is not None:
                            self._render_overlay(job, overlay)
                else:
                    idle_rounds += 1

                if job.finished.is_set() and idle_rounds >= self.idle_checks:
                    break

                if job.final_dir and job.final_dir.exists():
                    active_dir = job.final_dir

                time.sleep(poll_interval)
        finally:
            final_dir = job.final_dir or active_dir
            job.results["session"] = final_dir.name
            if job.end_iso is None:
                job.results["end"] = job.results.get("end") or job.start_iso
            self._write_results(job, final_dir)
            self._cleanup_frames(final_dir)
            self._close_overlay(job)
            self._notify_ble("COMPUTATION END")

    def _process_frame(self, frame_path: Path) -> Tuple[dict, Optional["np.ndarray"]]:
        if self.method == "cube" and HAS_CV and hasattr(cv2, "aruco"):
            return self._process_cube_frame(frame_path)
        if self.method == "custom":
            return (
                {
                    "file": frame_path.name,
                    "ok": False,
                    "reason": "custom_not_implemented",
                },
                None,
            )
        return (
            {
                "file": frame_path.name,
                "ok": False,
                "reason": "missing_opencv_contrib_or_invalid_method",
            },
            None,
        )

    def _process_cube_frame(self, frame_path: Path) -> Tuple[dict, Optional["np.ndarray"]]:
        pose_cfg = self.pose_cfg
        dict_name = pose_cfg.get("dictionary", "4X4_50")
        marker_size = float(pose_cfg.get("marker_size_mm", 55.0)) / 1000.0
        cube_size = float(pose_cfg.get("cube_size_mm", 60.0)) / 1000.0
        pair_strategy = pose_cfg.get("pair_strategy", "first")

        calib_path = self.cfg["pose"].get("camera_calibration_npz")
        if not calib_path:
            return (
                {
                    "file": frame_path.name,
                    "ok": False,
                    "reason": "no_calibration",
                },
                None,
            )

        try:
            result = estimate_cube_from_image(
                str(frame_path),
                calib_path,
                dict_name,
                marker_size,
                cube_size,
                pair_strategy=pair_strategy,
                return_overlay=True,
            )
        except FileNotFoundError:
            return (
                {
                    "file": frame_path.name,
                    "ok": False,
                    "reason": "read_fail",
                },
                None,
            )
        except ValueError:
            return (
                {
                    "file": frame_path.name,
                    "ok": False,
                    "reason": "no_markers",
                },
                None,
            )
        except Exception:
            return (
                {
                    "file": frame_path.name,
                    "ok": False,
                    "reason": "pose_fail",
                },
                None,
            )

        overlay = result.get("overlay")
        if overlay is not None:
            try:
                cv2.imwrite(str(frame_path), overlay)
            except Exception:
                overlay = None

        frame_entry = {
            "file": frame_path.name,
            "ok": True,
            "rvec": [float(x) for x in np.asarray(result["rvec"]).flatten()],
            "tvec": [float(x) for x in np.asarray(result["tvec"]).flatten()],
            "reproj_err": None,
            "num_markers": int(result.get("num_markers", 0)),
        }
        return frame_entry, overlay

    def _render_overlay(self, job: SessionJob, overlay) -> None:
        if not self.show_overlay or overlay is None:
            return
        window = job.overlay_window
        if window is None:
            window = f"{self.overlay_title} - {job.key}"
            job.overlay_window = window
        try:
            cv2.imshow(window, overlay)
            cv2.waitKey(1)
        except Exception as exc:
            log.warning(f"Overlay display failed: {exc}")
            job.overlay_window = None

    def _close_overlay(self, job: SessionJob) -> None:
        if not self.show_overlay:
            return
        if job.overlay_window and HAS_CV:
            try:
                cv2.destroyWindow(job.overlay_window)
            except Exception:
                pass
            job.overlay_window = None

    def _write_results(self, job: SessionJob, final_dir: Path) -> None:
        out_json = self.output_root / f"{final_dir.name}_pose.json"
        try:
            with out_json.open("w", encoding="utf-8") as f:
                json.dump(job.results, f, indent=2)
            log.info(f"Pose results written to {out_json.name}")
        except Exception as exc:
            log.error(f"Failed to write pose results: {exc}")

    def _cleanup_frames(self, final_dir: Path) -> None:
        if self.delete_frames and not self.debug:
            try:
                shutil.rmtree(final_dir)
                log.info(f"{final_dir.name} deleted (frames removed)")
            except Exception as exc:
                log.error(f"rmtree error: {exc}")
        else:
            log.info(
                f"frames kept (delete_frames={self.delete_frames}, debug={self.debug})"
            )

    def _notify_ble(self, message: str) -> None:
        try:
            asyncio.run_coroutine_threadsafe(self.ble_queue.put(message), self.loop)
        except RuntimeError:
            pass
