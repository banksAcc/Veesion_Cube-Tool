import asyncio
import json
import shutil
from pathlib import Path

try:
    import cv2
    import numpy as np
    HAS_CV = True
except Exception:
    cv2, np, HAS_CV = None, None, False

DICT_MAP = {
    "DICT_4X4_50":  getattr(cv2.aruco if HAS_CV else object, "DICT_4X4_50", None),
    "DICT_5X5_100":  getattr(cv2.aruco if HAS_CV else object, "DICT_5X5_50", None),
    "DICT_6X6_50":  getattr(cv2.aruco if HAS_CV else object, "DICT_6X6_50", None),
    "DICT_7X7_50":  getattr(cv2.aruco if HAS_CV else object, "DICT_7X7_50", None),
    "DICT_ARUCO_ORIGINAL": getattr(cv2.aruco if HAS_CV else object, "DICT_ARUCO_ORIGINAL", None),
}

def _load_calibration_npz(calib_path: str, K_key_override: str | None = None, D_key_override: str | None = None):
    """
    Ritorna (K, D) da un file .npz.
    Supporta vari nomi di chiavi: 'camera_matrix','K','mtx', ... e 'dist_coeffs','D','dist', ...
    Se il .npz contiene un dict salvato come arr_0, lo gestisce.
    """
    if not HAS_CV:
        raise RuntimeError("OpenCV non disponibile")

    data = np.load(calib_path, allow_pickle=True)
    keys = list(data.keys())

    # Se è stato salvato un dict intero come arr_0
    if len(keys) == 1 and keys[0].startswith("arr_"):
        maybe = data[keys[0]]
        if isinstance(maybe, dict):
            cand = maybe
        else:
            cand = {}
    else:
        cand = {k: data[k] for k in keys}

    # Override da config (se specificato)
    K = cand.get(K_key_override) if K_key_override else None
    D = cand.get(D_key_override) if D_key_override else None

    # Se non trovati via override, prova una lista di alias comuni
    if K is None:
        for kname in ["camera_matrix", "K", "mtx", "cameraMatrix", "intrinsic_matrix"]:
            if kname in cand:
                K = cand[kname]
                break
    if D is None:
        for dname in ["dist_coeffs", "D", "dist", "distCoeffs", "distortion_coefficients"]:
            if dname in cand:
                D = cand[dname]
                break

    if K is None or D is None:
        print(f"[POSE] calib npz keys trovate: {list(cand.keys())}")
        raise ValueError("File calibrazione .npz: manca 'camera_matrix/mtx/K' o 'dist_coeffs/dist/D'")

    # Normalizza forme/tipi
    K = np.asarray(K, dtype=np.float64).reshape(3, 3)
    D = np.asarray(D, dtype=np.float64).reshape(-1, 1)  # (N,1) accettato da OpenCV
    return K, D

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
        pose_cfg = self.cfg["pose"]["charuco"]
        dict_name = pose_cfg.get("dictionary", "DICT_5X5_100")
        squares_x = int(pose_cfg.get("squares_x", 5))
        squares_y = int(pose_cfg.get("squares_y", 7))
        square_len = float(pose_cfg.get("square_length_mm", 30.0))
        marker_len = float(pose_cfg.get("marker_length_mm", 22.0))

        dict_id = DICT_MAP.get(dict_name)
        if dict_id is None:
            for p in frames:
                res.append({"file": p.name, "ok": False, "reason": f"bad_dictionary:{dict_name}"})
            return res

        aruco_dict = cv2.aruco.getPredefinedDictionary(dict_id)
        board = cv2.aruco.CharucoBoard((squares_x, squares_y), square_len, marker_len, aruco_dict)

        calib_path = self.cfg["pose"].get("camera_calibration_npz")
        print(calib_path)
        if not calib_path:
            K, D = None, None
        else:
            data = np.load(calib_path)
            K = data.get("cameraMatrix")
            D = data.get("distCoeffs")

        for p in frames:
            img = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)  # preserva 8/16 bit
            if img is None:
                res.append({"file": p.name, "ok": False, "reason": "read_fail"})
                continue
            
            # converti in GRAY 8-bit per ArUco
            if len(img.shape) == 3:
                img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            if img.dtype != np.uint8:
                # normalizza a 8-bit mantenendo il contrasto
                maxv = float(np.iinfo(img.dtype).max) if img.dtype.kind in "ui" else float(img.max() or 1.0)
                img = cv2.convertScaleAbs(img, alpha=255.0/maxv)

            corners, ids, _ = cv2.aruco.detectMarkers(img, aruco_dict)
            if ids is None or len(ids) == 0:
                res.append({"file": p.name, "ok": False, "reason": "no_markers"})
                continue

            _, ch_corners, ch_ids = cv2.aruco.interpolateCornersCharuco(corners, ids, img, board)
            if ch_corners is None or ch_ids is None or len(ch_ids) < 4:
                res.append({"file": p.name, "ok": False, "reason": "few_charuco"})
                continue

            if K is not None and D is not None:
                retval, rvec, tvec = cv2.aruco.estimatePoseCharucoBoard(ch_corners, ch_ids, board, K, D, None, None)
                if not retval:
                    res.append({"file": p.name, "ok": False, "reason": "pose_fail"})
                    continue

                # (opzionale) errore di riproiezione semplice
                reproj_err = None
                try:
                    obj_pts = board.chessboardCorners[ch_ids.flatten()]
                    img_p, _ = cv2.projectPoints(obj_pts, rvec, tvec, K, D)
                    err = np.linalg.norm(img_p.reshape(-1,2) - ch_corners.reshape(-1,2), axis=1).mean()
                    reproj_err = float(err)
                except Exception:
                    pass

                res.append({
                    "file": p.name,
                    "ok": True,
                    "rvec": [float(x) for x in rvec.flatten()],
                    "tvec": [float(x) for x in tvec.flatten()],
                    "reproj_err": reproj_err,
                    "num_charuco": int(len(ch_ids)),
                })
            else:
                # senza calibrazione, niente posa affidabile
                res.append({"file": p.name, "ok": False, "reason": "no_calibration"})

        return res
