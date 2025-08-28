import asyncio
import json
import shutil
from pathlib import Path
from cube_minimal.cube_minimal.cube_pose.api import estimate_cube_from_image

try:
    import cv2
    import numpy as np
    HAS_CV = True
except Exception:
    cv2, np, HAS_CV = None, None, False

class PoseWorker:
    def __init__(self, cfg: dict, output_root: Path):
        self.cfg = cfg
        self.output_root = output_root
        self.queue: asyncio.Queue = asyncio.Queue()
        self.tasks: list[asyncio.Task] = []
        self.max_jobs = int(cfg["pose"].get("max_parallel_jobs", 1))
        self.enabled = bool(cfg["pose"].get("enabled", True))

    async def start(self):
        if not self.enabled:
            print("[POSE] disabilitato")
            return
        print(f"[POSE] starting workers = {self.max_jobs}")
        for _ in range(self.max_jobs):
            self.tasks.append(asyncio.create_task(self._worker()))

    async def stop(self):
        for _ in self.tasks:
            await self.queue.put(None)
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()

    async def _worker(self):
        while True:
            job = await self.queue.get()
            if job is None:
                break
            try:
                await asyncio.to_thread(self._process_session, job)
            except Exception as e:
                print(f"[POSE] job error: {e}")

    def _process_session(self, job: dict):
        session_dir = Path(job["session_dir"])
        start_iso = job["start"]
        end_iso   = job["end"]
        freq_ms   = int(job["freq_ms"])

        method = self.cfg["pose"].get("method", "charuco").lower()
        out_json = self.output_root / f"{session_dir.name}_pose.json"

        print(f"[POSE] Processing {session_dir.name} with method={method}")

        frames = sorted([p for p in session_dir.glob("*") if p.suffix.lower() in (".jpg",".jpeg",".png",".tif",".tiff")])
        results = {
            "session": session_dir.name,
            "start": start_iso,
            "end": end_iso,
            "frequency_ms": freq_ms,
            "method": method,
            "frames": [],
        }

        if method == "charuco" and HAS_CV and hasattr(cv2, "aruco"):
            results["frames"] = self._pose_charuco(frames)
        elif method == "custom":
            for p in frames:
                results["frames"].append({
                    "file": p.name, "ok": False, "reason": "custom_not_implemented"
                })
        else:
            reason = "missing_opencv_contrib_or_invalid_method"
            for p in frames:
                results["frames"].append({"file": p.name, "ok": False, "reason": reason})

        with out_json.open("w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)

        # cleanup
        delete_frames = bool(self.cfg["pose"].get("delete_frames_after_processing", True))
        debug = bool(self.cfg["runtime"].get("debug", True))
        if delete_frames and not debug:
            try:
                shutil.rmtree(session_dir)
                print(f"[POSE] {session_dir.name} eliminata (frames rimossi)")
            except Exception as e:
                print(f"[POSE] rmtree error: {e}")
        else:
            print(f"[POSE] frames conservati (delete_frames={delete_frames}, debug={debug})")

    def _pose_charuco(self, frames: list[Path]) -> list[dict]:
        res = []
        pose_cfg = self.cfg["pose"]["cube"]
        dict_name = pose_cfg.get("dictionary", "4X4_50")
        marker_size = float(pose_cfg.get("marker_size_mm", 55.0)) / 1000.0
        cube_size = float(pose_cfg.get("cube_size_mm", 60.0)) / 1000.0
        pair_strategy = pose_cfg.get("pair_strategy", "first")

        calib_path = self.cfg["pose"].get("camera_calibration_npz")
        if not calib_path:
            for p in frames:
                res.append({"file": p.name, "ok": False, "reason": "no_calibration"})
            return res

        for p in frames:
            try:
                result = estimate_cube_from_image(
                    str(p),
                    calib_path,
                    dict_name,
                    marker_size,
                    cube_size,
                    pair_strategy=pair_strategy,
                    return_overlay=True,
                )
            except FileNotFoundError:
                res.append({"file": p.name, "ok": False, "reason": "read_fail"})
                continue
            except ValueError:
                res.append({"file": p.name, "ok": False, "reason": "no_markers"})
                continue
            except Exception:
                res.append({"file": p.name, "ok": False, "reason": "pose_fail"})
                continue
            
            overlay = result.get("overlay")
            if overlay is not None:
                try:
                    cv2.imwrite(str(p), overlay)
                except Exception:
                    # if saving overlay fails, keep processing without altering result
                    pass
        
            res.append({
                "file": p.name,
                "ok": True,
                "rvec": [float(x) for x in np.asarray(result["rvec"]).flatten()],
                "tvec": [float(x) for x in np.asarray(result["tvec"]).flatten()],
                "reproj_err": None,
                "num_markers": int(result.get("num_markers", 0)),
            })

        return res
