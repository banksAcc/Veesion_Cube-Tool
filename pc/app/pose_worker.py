"""Asynchronous worker that computes pose from captured frames."""

from __future__ import annotations

import asyncio
import csv
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

# Importa le funzioni di caricamento e l'API di stima
from algo import (
    estimate_truncated_ico_from_image,
    load_camera_calibration,
    load_ico_transforms
)

from config_models import AppConfig, IcoPoseConfig
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
    save_overlay: bool = True
    end_iso: Optional[str] = None
    finished: asyncio.Event = field(default_factory=asyncio.Event)
    task: Optional[asyncio.Task] = None
    overlay_paths: List[Path] = field(default_factory=list)


class PoseWorker:
    """Asynchronous worker that estimates ico pose for capture sessions."""

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
        self.pose_cfg_ico = cfg.pose.ico
        self.save_overlay = bool(cfg.pose.save_overlay)
        self.save_executor = ThreadPoolExecutor(max_workers=1)

        # Cache per evitare di ricaricare file a ogni frame
        self._cached_calib_path: Optional[str] = None
        self._K: Optional[np.ndarray] = None
        self._dist: Optional[np.ndarray] = None
        self._cached_trans_path: Optional[str] = None
        self._transforms: Optional[dict] = None

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
            save_overlay=self.save_overlay,
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
            await self._process_session_stream(job, loop)

            if not job.finished.is_set():
                await job.finished.wait()

            if job.end_iso is None:
                job.results["end"] = job.results.get("end") or job.start_iso
        finally:
            self._write_results(job)
            self._cleanup_frames(job)
            self._notify_ble(BLE_COMPUTATION_END)

    async def _process_session_stream(
        self, job: SessionJob, loop: asyncio.AbstractEventLoop
    ) -> None:
        while True:
            packet = await job.frame_queue.get()
            if packet is None:
                break

            frame_result, overlay = await asyncio.to_thread(
                self._process_frame_packet, job, packet
            )
            job.results["frames"].append(frame_result)

            overlay_path = None
            if overlay is not None and job.save_overlay:
                overlay_path = self._derive_overlay_path(job, packet)
                if overlay_path is not None:
                    job.overlay_paths.append(overlay_path)
                    frame_result["overlay_file"] = overlay_path.name

            if job.save_frames:
                await self._save_packet(job, packet, overlay, overlay_path, loop)

            packet.frame = None  # release reference as soon as possible

    async def _save_packet(
        self,
        job: SessionJob,
        packet: FramePacket,
        overlay: Any,
        overlay_path: Optional[Path],
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        if not HAS_CV:
            return
        image = packet.frame
        if image is None and overlay is None:
            return

        path = packet.save_path
        if path is None:
            if job.save_dir is None:
                return
            path = Path(job.save_dir) / packet.filename

        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                if image is not None:
                    ok = cv2.imwrite(str(path), image)
                    if not ok:
                        log.warning(f"cv2.imwrite returned False for {path.name}")
                if overlay is not None and overlay_path is not None:
                    overlay_path.parent.mkdir(parents=True, exist_ok=True)
                    ok_overlay = cv2.imwrite(str(overlay_path), overlay)
                    if not ok_overlay:
                        log.warning(
                            f"cv2.imwrite returned False for {overlay_path.name}"
                        )
            except Exception as exc:
                log.warning(f"Failed to write frame {path.name}: {exc}")
                return

        try:
            await loop.run_in_executor(self.save_executor, _write)
        except Exception as exc:
            log.warning(f"Failed to persist frame {path.name}: {exc}")

    def _derive_overlay_path(
        self, job: SessionJob, packet: FramePacket
    ) -> Optional[Path]:
        base_path = packet.save_path
        if base_path is None:
            if job.save_dir is None:
                return None
            base_path = Path(job.save_dir) / packet.filename
        stem = base_path.stem
        suffix = base_path.suffix
        return base_path.with_name(f"{stem}_overlay{suffix}")

    def _cleanup_frames(self, job: SessionJob) -> None:
        if not job.save_frames:
            job.overlay_paths.clear()
            return
        if job.save_overlay:
            job.overlay_paths.clear()
            return
        directory = job.save_dir
        if directory is None:
            job.overlay_paths.clear()
            return
        try:
            for overlay_path in directory.glob("*_overlay.*"):
                try:
                    overlay_path.unlink()
                except FileNotFoundError:
                    continue
                except OSError as exc:
                    log.debug(f"Could not remove {overlay_path.name}: {exc}")
        except OSError as exc:
            log.debug(f"Overlay cleanup failed in {directory}: {exc}")
        job.overlay_paths.clear()

    def _process_frame_packet(
        self, job: SessionJob, packet: FramePacket
    ) -> Tuple[dict[str, Any], Optional["np.ndarray"]]:
        if self.method == "ico" and HAS_CV and hasattr(cv2, "aruco"):
            return self._process_ico_frame(job, packet)
        
        return (
            {
                "file": packet.filename,
                "ok": False,
                "reason": f"invalid_method_{self.method}",
            },
            None,
        )

    def _process_ico_frame(
        self, job: SessionJob, packet: FramePacket
    ) -> Tuple[dict[str, Any], Optional["np.ndarray"]]:
        
        pose_cfg = self.pose_cfg_ico
        dict_name = pose_cfg.dictionary
        # Conversione mm -> metri
        marker_size = float(pose_cfg.marker_size_mm) / 1000.0 
        
        # Percorsi file
        transform_path = pose_cfg.transform_file
        calib_path = self.cfg.pose.camera_calibration_npz

        if not calib_path:
            return (
                {"file": packet.filename, "ok": False, "reason": "no_calibration"},
                None,
            )

        # --- 1. CARICAMENTO E CACHING RISORSE (K, Dist, Transforms) ---
        # A. Calibrazione Camera
        if self._cached_calib_path != str(calib_path):
            try:
                self._K, self._dist = load_camera_calibration(str(calib_path))
                self._cached_calib_path = str(calib_path)
            except Exception as e:
                return ({"file": packet.filename, "ok": False, "reason": f"calib_load_err: {e}"}, None)

        # B. Trasformazioni Faccia->Corpo (con SCALING)
        if self._cached_trans_path != str(transform_path):
            try:
                raw_transforms = load_ico_transforms(str(transform_path))
                
                # Applichiamo qui la scala del raggio reale.
                # Cerchiamo radius_m nel config, altrimenti default 0.11
                ico_radius = getattr(pose_cfg, 'radius_m', 0.11) 
                
                scaled_transforms = {}
                for key, T in raw_transforms.items():
                    T_real = T.copy()
                    # Scaliamo la traslazione (ultime 3 righe, 4a colonna)
                    T_real[:3, 3] *= ico_radius
                    scaled_transforms[key] = T_real
                
                self._transforms = scaled_transforms
                self._cached_trans_path = str(transform_path)
            except Exception as e:
                 return ({"file": packet.filename, "ok": False, "reason": f"trans_load_err: {e}"}, None)

        # --- 2. STIMA POSA ---
        try:
            result = estimate_truncated_ico_from_image(
                image=packet.frame,
                K=self._K,
                dist=self._dist,
                transforms=self._transforms,
                aruco_dict=dict_name,
                marker_size=marker_size,
                
                # Parametri Tuning Stabilità (Override dei default per robustezza)
                min_marker_area_px=250.0,
                weight_exponent=2.1,         # Consigliato 2.0 per stabilità
                outlier_distance_threshold=0.17, # 8cm tolleranza
                
                return_overlay=True,
                timestamp=packet.timestamp,
            )
            
        except ValueError:
            return (
                {"file": packet.filename, "ok": False, "reason": "no_markers"},
                None,
            )
        except Exception as e:
            # Stampa errore per debug e ritorna stato fallito
            print(f"Errore critico in pose_fail: {e}") 
            return (
                {"file": packet.filename, "ok": False, "reason": f"pose_fail: {str(e)}"},
                None,
            )

        # --- 3. FORMATTAZIONE OUTPUT ---
        overlay = result.get("overlay")

        # Flattening sicuro per JSON
        rvec_flat = result["rvec"].flatten().tolist()
        tvec_flat = result["tvec"].flatten().tolist()

        frame_entry: dict[str, Any] = {
            "file": packet.filename,
            "ok": True,
            "rvec": rvec_flat,
            "tvec": tvec_flat,
            "reproj_err": None,
            "num_markers": int(result.get("num_markers", 0)),
            "timestamp": packet.iso_timestamp,
        }

        if "filter_debug" in result and result["filter_debug"]:
            frame_entry["marker_filter"] = result["filter_debug"]

        return frame_entry, overlay

    def _write_results(self, job: SessionJob) -> None:
        label = job.label
        out_json = self.output_root / f"{label}_pose.json"
        try:
            with out_json.open("w", encoding="utf-8") as f:
                json.dump(job.results, f, indent=2)
            log.info(f"Pose results written to {out_json.name}")
        except Exception as exc:
            log.error(f"Failed to write pose results: {exc}")

        # CSV semplificato per ICO (solo rvec/tvec base, niente tip/wand)
        out_csv = self.output_root / f"{label}_pose.csv"
        try:
            with out_csv.open("w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        "frame_index",
                        "timestamp",
                        "ok",
                        "tx", "ty", "tz",
                        "rx", "ry", "rz",
                        "num_markers"
                    ]
                )
                for idx, frame in enumerate(job.results.get("frames", []), start=1):
                    ok = frame.get("ok", False)
                    tvec = frame.get("tvec", [None]*3)
                    rvec = frame.get("rvec", [None]*3)
                    num_mk = frame.get("num_markers", 0)

                    t_vals = ["" if v is None else f"{v:.6f}" for v in tvec]
                    r_vals = ["" if v is None else f"{v:.6f}" for v in rvec]
                    
                    writer.writerow([
                        idx,
                        frame.get("timestamp", ""),
                        ok,
                        *t_vals,
                        *r_vals,
                        num_mk
                    ])
            log.info(f"Pose CSV written to {out_csv.name}")
        except Exception as exc:
            log.error(f"Failed to write pose CSV: {exc}")

    def _notify_ble(self, message: BleMessage) -> None:
        try:
            asyncio.run_coroutine_threadsafe(self.ble_queue.put(message), self.loop)
        except RuntimeError:
            pass