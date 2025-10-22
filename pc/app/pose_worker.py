"""Asynchronous worker that computes pose from captured frames."""

from __future__ import annotations

import asyncio
import csv
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, TYPE_CHECKING

from cube_minimal.cube_pose.api import estimate_cube_from_image
from cube_minimal.cube_pose.filtering.marker_filter import MarkerFilter

from config_models import AppConfig, CubePoseConfig
from logger import get_logger
from messages import (
    BLE_COMPUTATION_END,
    BLE_COMPUTATION_START,
    BleMessage,
    PoseEndMessage,
    PoseStartMessage,
    PoseWorkerPayload,
)
from stream import FramePacket

try:
    import cv2  # type: ignore[import]
    import numpy as np  # type: ignore[import]
    HAS_CV = True
except Exception:  # pragma: no cover - optional dependency
    cv2 = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]
    HAS_CV = False

if TYPE_CHECKING:  # pragma: no cover - typing helper
    import numpy as np

log = get_logger("POSE")

@dataclass
class SessionJob:
    """Track state for an in-flight pose estimation session."""

    key: str
    frame_queue: asyncio.Queue[Optional[FramePacket]]
    freq_ms: int
    start_iso: str
    results: dict[str, Any]
    label: str
    save_frames: bool
    save_dir: Optional[Path] = None
    end_iso: Optional[str] = None
    finished: asyncio.Event = field(default_factory=asyncio.Event)
    task: Optional[asyncio.Task] = None
    marker_filter: Optional[MarkerFilter] = None


class PoseWorker:
    """Asynchronous worker that estimates cube pose for capture sessions."""

    def __init__(
        self,
        cfg: AppConfig,
        output_root: Path,
        ble_queue: asyncio.Queue[Optional[BleMessage]],
    ):
        self.cfg = cfg
        self.output_root = output_root
        self.queue: asyncio.Queue[Optional[PoseWorkerPayload]] = asyncio.Queue()
        self.tasks: list[asyncio.Task] = []
        self.max_jobs = int(cfg.pose.max_parallel_jobs)
        self.enabled = bool(cfg.pose.enabled)
        self.ble_queue = ble_queue
        try:
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            self.loop = asyncio.get_event_loop()

        self.sessions: Dict[str, SessionJob] = {}
        self.method = cfg.pose.method.lower()
        self.pose_cfg: CubePoseConfig = cfg.pose.cube
        self.wand_offset = float(self.pose_cfg.wand_offset_m)
        self.wand_directions = dict(self.pose_cfg.wand_directions)
        self.save_executor = ThreadPoolExecutor(max_workers=1)

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

    async def start(self) -> None:
        """Spawn worker tasks if pose estimation is enabled."""
        if not self.enabled:
            log.info("disabled")
            return
        log.info(f"starting workers = {self.max_jobs}")
        for _ in range(self.max_jobs):
            self.tasks.append(asyncio.create_task(self._worker()))

    async def stop(self) -> None:
        """Signal workers to exit and wait for completion."""
        for job in list(self.sessions.values()):
            job.finished.set()
            try:
                job.frame_queue.put_nowait(None)
            except asyncio.QueueFull:
                pass
        for _ in self.tasks:
            await self.queue.put(None)
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()
        await asyncio.gather(
            *(job.task for job in list(self.sessions.values()) if job.task),
            return_exceptions=True,
        )
        self.sessions.clear()
        self.save_executor.shutdown(wait=True)

    async def _worker(self) -> None:
        """Consume jobs from the queue and dispatch session handling."""
        while True:
            job = await self.queue.get()
            if job is None:
                break
            if isinstance(job, PoseStartMessage):
                self._handle_start(job)
            elif isinstance(job, PoseEndMessage):
                self._handle_end(job)
            else:
                log.warning(f"Unknown pose job payload: {job!r}")

    def _handle_start(self, payload: PoseStartMessage) -> None:
        session_key = payload.session_key
        if session_key in self.sessions:
            log.warning(f"Session {session_key} already tracked -> ignoring start")
            return

        session_dir = payload.session_dir
        frame_queue = payload.frame_queue
        freq_ms = int(payload.freq_ms)
        label = payload.label or session_dir.name
        save_frames = bool(payload.save_frames)
        save_dir = payload.save_dir
        results: dict[str, Any] = {
            "session": label,
            "start": payload.start,
            "end": None,
            "frequency_ms": freq_ms,
            "method": self.method,
            "frames": [],
        }
        job = SessionJob(
            key=session_key,
            frame_queue=frame_queue,
            freq_ms=freq_ms,
            start_iso=payload.start,
            results=results,
            label=label,
            save_frames=save_frames,
            save_dir=save_dir,
            marker_filter=self._create_marker_filter(),
        )
        job.task = asyncio.create_task(self._run_session(job))
        self.sessions[session_key] = job
        log.info(f"Pose session started for {label}")

    def _handle_end(self, payload: PoseEndMessage) -> None:
        session_key = payload.session_key
        job = self.sessions.get(session_key)
        if job is None:
            log.warning(f"Pose END for unknown session {session_key}")
            return
        if payload.save_dir:
            job.save_dir = payload.save_dir
        job.end_iso = payload.end
        job.results["end"] = job.end_iso
        job.finished.set()
        log.info(f"Pose session finishing for {job.label}")

    async def _run_session(self, job: SessionJob) -> None:
        try:
            await self._consume_session(job)
        finally:
            self.sessions.pop(job.key, None)

    async def _consume_session(self, job: SessionJob) -> None:
        self._notify_ble(BLE_COMPUTATION_START)
        loop = asyncio.get_running_loop()
        try:
            while True:
                packet = await job.frame_queue.get()
                if packet is None:
                    break

                frame_result, overlay = await asyncio.to_thread(
                    self._process_frame_packet, job, packet
                )
                job.results["frames"].append(frame_result)

                if job.save_frames:
                    await self._save_packet(job, packet, overlay, loop)

                packet.frame = None  # release reference as soon as possible

            if not job.finished.is_set():
                await job.finished.wait()

            if job.end_iso is None:
                job.results["end"] = job.results.get("end") or job.start_iso
        finally:
            self._write_results(job)
            self._notify_ble(BLE_COMPUTATION_END)

    async def _save_packet(
        self,
        job: SessionJob,
        packet: FramePacket,
        overlay: Any,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        if not HAS_CV:
            return
        image = overlay if overlay is not None else packet.frame
        if image is None:
            return

        path = packet.save_path
        if path is None:
            if job.save_dir is None:
                return
            path = Path(job.save_dir) / packet.filename

        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                ok = cv2.imwrite(str(path), image)
            except Exception as exc:  # pragma: no cover - depends on cv2 backend
                log.warning(f"Failed to write frame {path.name}: {exc}")
                return
            if not ok:
                log.warning(f"cv2.imwrite returned False for {path.name}")

        try:
            await loop.run_in_executor(self.save_executor, _write)
        except Exception as exc:  # pragma: no cover - executor errors are rare
            log.warning(f"Failed to persist frame {path.name}: {exc}")

    def _process_frame_packet(
        self, job: SessionJob, packet: FramePacket
    ) -> Tuple[dict[str, Any], Optional["np.ndarray"]]:
        if self.method == "cube" and HAS_CV and hasattr(cv2, "aruco"):
            return self._process_cube_frame(job, packet)
        if self.method == "custom":
            return (
                {
                    "file": packet.filename,
                    "ok": False,
                    "reason": "custom_not_implemented",
                },
                None,
            )
        return (
            {
                "file": packet.filename,
                "ok": False,
                "reason": "missing_opencv_contrib_or_invalid_method",
            },
            None,
        )

    def _create_marker_filter(self) -> MarkerFilter:
        cfg = self.pose_cfg.marker_filter
        active = bool(cfg.active_marker_filter)
        try_adjust = bool(cfg.try_adj_marker)
        threshold = float(cfg.area_threshold_px or 0.0)
        return MarkerFilter(
            active=active,
            try_adjust=try_adjust,
            area_threshold_px=threshold,
        )

    def _process_cube_frame(
        self, job: SessionJob, packet: FramePacket
    ) -> Tuple[dict[str, Any], Optional["np.ndarray"]]:
        pose_cfg = self.pose_cfg
        dict_name = pose_cfg.dictionary
        marker_size = float(pose_cfg.marker_size_mm) / 1000.0
        cube_size = float(pose_cfg.cube_size_mm) / 1000.0
        pair_strategy = pose_cfg.pair_strategy

        calib_path = self.cfg.pose.camera_calibration_npz
        if not calib_path:
            return (
                {
                    "file": packet.filename,
                    "ok": False,
                    "reason": "no_calibration",
                },
                None,
            )

        try:
            result = estimate_cube_from_image(
                packet.frame,
                str(calib_path),
                dict_name,
                marker_size,
                cube_size,
                pair_strategy=pair_strategy,
                return_overlay=True,
                marker_filter=job.marker_filter,
                timestamp=packet.timestamp,
            )
        except ValueError:
            return (
                {
                    "file": packet.filename,
                    "ok": False,
                    "reason": "no_markers",
                },
                None,
            )
        except Exception:
            return (
                {
                    "file": packet.filename,
                    "ok": False,
                    "reason": "pose_fail",
                },
                None,
            )

        overlay = result.get("overlay")

        frame_entry: dict[str, Any] = {
            "file": packet.filename,
            "ok": True,
            "rvec": [float(x) for x in np.asarray(result["rvec"]).flatten()],
            "tvec": [float(x) for x in np.asarray(result["tvec"]).flatten()],
            "reproj_err": None,
            "num_markers": int(result.get("num_markers", 0)),
        }

        filter_info = result.get("marker_filter") or {}
        if filter_info.get("discarded_ids") or filter_info.get("corrected_ids"):
            frame_entry["marker_filter"] = filter_info

        frame_entry["timestamp"] = packet.iso_timestamp

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


    def _direction_from_spec(self, spec: Any) -> Optional["np.ndarray"]:
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

    def _compute_wand_tip(self, result: dict) -> Optional[Tuple["np.ndarray", "np.ndarray"]]:
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

    def _compute_tip_rotation(
        self, result: dict, wand_dir: "np.ndarray"
    ) -> Optional["np.ndarray"]:
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

    def _write_results(self, job: SessionJob) -> None:
        label = job.label
        out_json = self.output_root / f"{label}_pose.json"
        try:
            with out_json.open("w", encoding="utf-8") as f:
                json.dump(job.results, f, indent=2)
            log.info(f"Pose results written to {out_json.name}")
        except Exception as exc:
            log.error(f"Failed to write pose results: {exc}")

        out_csv = self.output_root / f"{label}_pose.csv"
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

    def _notify_ble(self, message: BleMessage) -> None:
        try:
            asyncio.run_coroutine_threadsafe(self.ble_queue.put(message), self.loop)
        except RuntimeError:
            pass
