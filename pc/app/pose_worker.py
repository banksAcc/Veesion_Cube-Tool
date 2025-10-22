"""Asynchronous worker that computes pose from captured frames."""

import asyncio
import csv
import json
import shutil
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

from cube_minimal.cube_pose.api import estimate_cube_from_image
from cube_minimal.cube_pose.filtering import MarkerFilter

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
    marker_filter: Optional[MarkerFilter] = None


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
        self.keep_frames = (not self.delete_frames) or self.debug
        self.file_settle = max(0.0, float(cfg["pose"].get("stream_file_settle_ms", 120)) / 1000.0)
        self.idle_checks = int(cfg["pose"].get("stream_idle_checks", 3))
        self.poll_floor = float(cfg["pose"].get("stream_poll_interval_ms", 100)) / 1000.0
        self.pose_cfg = cfg["pose"].get("cube", {})
        self.wand_offset = float(self.pose_cfg.get("wand_offset_m", 0.0))
        self.wand_directions = self._build_wand_direction_map(
            self.pose_cfg.get("wand_directions", {})
        )
        filter_cfg = self.pose_cfg.get("marker_filter", {})
        self.marker_filter_active = bool(filter_cfg.get("active_marker_filter", False))
        self.marker_filter_try_adj = bool(filter_cfg.get("try_adj_marker", False))
        area_threshold = filter_cfg.get("min_area_px")
        self.marker_filter_area_threshold = (
            float(area_threshold) if area_threshold is not None else None
        )

    @staticmethod
    def _rotation_matrix_to_euler_zyx(R: "np.ndarray") -> Optional["np.ndarray"]:
        if np is None:
            return None
        matrix = np.asarray(R, dtype=float)
        if matrix.shape != (3, 3):
            return None

        sy = float(np.sqrt(matrix[0, 0] ** 2 + matrix[1, 0] ** 2))
        singular = sy < 1e-9

        if not singular:
            rz = float(np.arctan2(matrix[1, 0], matrix[0, 0]))
            ry = float(np.arctan2(-matrix[2, 0], sy))
            rx = float(np.arctan2(matrix[2, 1], matrix[2, 2]))
        else:
            rz = float(np.arctan2(-matrix[0, 1], matrix[1, 1]))
            ry = float(np.arctan2(-matrix[2, 0], sy))
            rx = 0.0

        return np.array([rz, ry, rx], dtype=float)

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
            marker_filter=MarkerFilter(
                active=self.marker_filter_active,
                try_adjust=self.marker_filter_try_adj,
                area_threshold_px=self.marker_filter_area_threshold,
            ),
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
                else:
                    idle_rounds += 1

                for frame_path in new_frames:
                    try:
                        mtime = frame_path.stat().st_mtime
                    except FileNotFoundError:
                        continue

                    if time.time() - mtime < self.file_settle:
                        continue

                    frame_result, overlay = self._process_frame(
                        frame_path,
                        marker_filter=job.marker_filter,
                        frame_timestamp=mtime,
                    )
                    job.results["frames"].append(frame_result)
                    job.processed.add(frame_path.name)

                    if overlay is not None and self.keep_frames and HAS_CV:
                        try:
                            cv2.imwrite(str(frame_path), overlay)
                        except Exception as exc:
                            log.warning(f"overlay write failed: {exc}")

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
            self._notify_ble("COMPUTATION END")

    def _process_frame(
        self,
        frame_path: Path,
        marker_filter: Optional[MarkerFilter] = None,
        frame_timestamp: Optional[float] = None,
    ) -> Tuple[dict, Optional["np.ndarray"]]:
        if self.method == "cube" and HAS_CV and hasattr(cv2, "aruco"):
            return self._process_cube_frame(
                frame_path,
                marker_filter=marker_filter,
                frame_timestamp=frame_timestamp,
            )
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

    def _process_cube_frame(
        self,
        frame_path: Path,
        marker_filter: Optional[MarkerFilter] = None,
        frame_timestamp: Optional[float] = None,
    ) -> Tuple[dict, Optional["np.ndarray"]]:
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
                marker_filter=marker_filter,
                frame_timestamp=frame_timestamp,
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
        except ValueError as exc:
            reason = "no_markers"
            if "filter" in str(exc).lower():
                reason = "markers_filtered"
            return (
                {
                    "file": frame_path.name,
                    "ok": False,
                    "reason": reason,
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

        frame_entry = {
            "file": frame_path.name,
            "ok": True,
            "rvec": [float(x) for x in np.asarray(result["rvec"]).flatten()],
            "tvec": [float(x) for x in np.asarray(result["tvec"]).flatten()],
            "reproj_err": None,
            "num_markers": int(result.get("num_markers", 0)),
        }

        frame_entry["discarded_marker_ids"] = list(
            result.get("discarded_marker_ids", [])
        )
        frame_entry["corrected_marker_ids"] = list(
            result.get("corrected_marker_ids", [])
        )

        timestamp = self._extract_timestamp(frame_path)
        if timestamp is not None:
            frame_entry["timestamp"] = timestamp

        wand_tip = self._compute_wand_tip(result)
        if wand_tip is not None:
            tip_pos, wand_dir = wand_tip
            frame_entry["tvec_tip"] = [float(x) for x in tip_pos]
            frame_entry["wand_direction"] = [float(x) for x in wand_dir]

            tip_rot = self._compute_tip_rotation(result, wand_dir)
            if tip_rot is not None:
                euler = self._rotation_matrix_to_euler_zyx(tip_rot)
                if euler is not None:
                    frame_entry["euler_tip"] = [float(x) for x in euler]
                    frame_entry["tip_pose"] = [
                        float(tip_pos[0]),
                        float(tip_pos[1]),
                        float(tip_pos[2]),
                        float(euler[0]),
                        float(euler[1]),
                        float(euler[2]),
                    ]

        return frame_entry, overlay


    def _build_wand_direction_map(self, raw_cfg):
        mapping = {}
        if not isinstance(raw_cfg, dict):
            return mapping
        for key, spec in raw_cfg.items():
            try:
                marker_id = int(key)
            except (TypeError, ValueError):
                log.warning(f"Invalid marker id in wand_directions: {key!r}")
                continue
            mapping[marker_id] = spec
        return mapping

    def _direction_from_spec(self, spec):
        if np is None:
            return None
        if isinstance(spec, (list, tuple)):
            vec = np.asarray(spec, dtype=float)
            if vec.shape != (3,):
                log.warning(f"Invalid wand direction vector length: {spec!r}")
                return None
            norm = float(np.linalg.norm(vec))
            if norm < 1e-9:
                return None
            return vec / norm
        if isinstance(spec, str):
            token = spec.strip().upper()
            if not token:
                return None
            sign = 1.0
            if token[0] in {"+", "-"}:
                sign = -1.0 if token[0] == "-" else 1.0
                token = token[1:]
            axis_map = {
                "X": np.array([1.0, 0.0, 0.0], dtype=float),
                "Y": np.array([0.0, 1.0, 0.0], dtype=float),
                "Z": np.array([0.0, 0.0, 1.0], dtype=float),
            }
            base = axis_map.get(token)
            if base is None:
                log.warning(f"Unknown wand axis token: {spec!r}")
                return None
            return base * sign
        log.warning(f"Unsupported wand direction spec: {spec!r}")
        return None

    def _compute_wand_tip(self, result: dict):
        if np is None or self.wand_offset == 0:
            return None
        markers = result.get("markers") or []
        direction_vectors = []
        for marker in markers:
            marker_id = marker.get("id")
            if marker_id not in self.wand_directions:
                continue
            local = self._direction_from_spec(self.wand_directions[marker_id])
            if local is None:
                continue
            R_marker = np.asarray(marker.get("R"), dtype=float)
            if R_marker.shape != (3, 3):
                continue
            direction_cam = R_marker @ local
            norm = float(np.linalg.norm(direction_cam))
            if norm < 1e-9:
                continue
            direction_vectors.append(direction_cam / norm)
        if not direction_vectors:
            return None
        wand_dir = np.mean(direction_vectors, axis=0)
        norm = float(np.linalg.norm(wand_dir))
        if norm < 1e-9:
            return None
        wand_dir /= norm
        tvec = np.asarray(result.get("tvec"), dtype=float).reshape(3,)
        tip = tvec + wand_dir * float(self.wand_offset)
        return tip, wand_dir

    def _compute_tip_rotation(self, result: dict, wand_dir: "np.ndarray") -> Optional["np.ndarray"]:
        if np is None:
            return None
        base_R = np.asarray(result.get("R"), dtype=float)
        if base_R.shape != (3, 3):
            return None

        direction = np.asarray(wand_dir, dtype=float).reshape(3,)
        norm = float(np.linalg.norm(direction))
        if norm < 1e-9:
            return None
        z_axis = direction / norm

        candidates = [base_R[:, i] for i in range(3)]
        candidates.extend([np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0])])

        x_axis = None
        for cand in candidates:
            proj = cand - np.dot(cand, z_axis) * z_axis
            proj_norm = float(np.linalg.norm(proj))
            if proj_norm >= 1e-6:
                x_axis = proj / proj_norm
                break
        if x_axis is None:
            return None

        y_axis = np.cross(z_axis, x_axis)
        y_norm = float(np.linalg.norm(y_axis))
        if y_norm < 1e-6:
            return None
        y_axis /= y_norm

        x_axis = np.cross(y_axis, z_axis)
        x_norm = float(np.linalg.norm(x_axis))
        if x_norm < 1e-6:
            return None
        x_axis /= x_norm

        return np.column_stack((x_axis, y_axis, z_axis))

    @staticmethod
    def _extract_timestamp(frame_path: Path) -> Optional[str]:
        stem = frame_path.stem
        parts = stem.split("_")
        if len(parts) < 3:
            return None
        date_part = parts[-2]
        time_part = parts[-1]
        try:
            dt = datetime.strptime(f"{date_part}_{time_part}", "%Y%m%d_%H%M%S")
        except ValueError:
            return None
        return dt.isoformat()

    def _write_results(self, job: SessionJob, final_dir: Path) -> None:
        out_json = self.output_root / f"{final_dir.name}_pose.json"
        try:
            with out_json.open("w", encoding="utf-8") as f:
                json.dump(job.results, f, indent=2)
            log.info(f"Pose results written to {out_json.name}")
        except Exception as exc:
            log.error(f"Failed to write pose results: {exc}")

        out_csv = self.output_root / f"{final_dir.name}_pose.csv"
        try:
            with out_csv.open("w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        "frame_index",
                        "timestamp",
                        "ok",
                        "tip_x",
                        "tip_y",
                        "tip_z",
                        "tip_rz",
                        "tip_ry",
                        "tip_rx",
                    ]
                )
                for idx, frame in enumerate(job.results.get("frames", []), start=1):
                    euler = frame.get("euler_tip") or [None, None, None]
                    tip = frame.get("tvec_tip") or [None, None, None]
                    tip_vals = ["" if v is None else f"{v:.9f}" for v in tip]
                    euler_vals = ["" if v is None else f"{v:.9f}" for v in euler]
                    writer.writerow(
                        [
                            idx,
                            frame.get("timestamp", ""),
                            frame.get("ok", False),
                            *tip_vals,
                            *euler_vals,
                        ]
                    )
            log.info(f"Pose CSV written to {out_csv.name}")
        except Exception as exc:
            log.error(f"Failed to write pose CSV: {exc}")

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
