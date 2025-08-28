import shutil
import time
from pathlib import Path
from typing import Callable, Optional

try:
    import cv2
except Exception:
    cv2 = None

class BaseCapture:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.image_format = cfg["capture"].get("image_format", "jpg").lower()
        self.jpeg_quality = int(cfg["capture"].get("jpeg_quality", 90))

    def _save_image(self, frame, path: Path):
        if frame is None:
            raise RuntimeError("Frame is None - cannot save")

        fmt = self.image_format
        if fmt in ("png",):
            ok = cv2.imwrite(str(path), frame)
        elif fmt in ("tif", "tiff"):
            # opzionale: compressione da config
            comp_map = {"none": 1, "lzw": 2, "packbits": 3, "deflate": 4}
            comp_name = str(self.cfg["capture"].get("tiff_compression", "none")).lower()
            comp = comp_map.get(comp_name, 1)
            ok = cv2.imwrite(str(path), frame, [int(cv2.IMWRITE_TIFF_COMPRESSION), comp])
        else:
            ok = cv2.imwrite(str(path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality])

        if not ok:
            raise RuntimeError(f"Failed to write image: {path}")


class CameraCapture(BaseCapture):
    def __init__(self, cfg: dict):
        super().__init__(cfg)
        self.cam = None

    def capture_loop(self, dest_dir: Path, freq_ms: int, stop_evt, log: Callable[[str], None]):
        if cv2 is None:
            log("[CAPTURE] OpenCV non disponibile: impossibile usare la camera")
            return

        cam_type = str(self.cfg["capture"].get("camera_type", "webcam")).lower()
        if cam_type == "webcam":
            cam_id = int(self.cfg["capture"].get("camera_id", 0))
            self.cam = cv2.VideoCapture(cam_id)
            if not self.cam.isOpened():
                log(f"[CAPTURE] Unable to open webcam id={cam_id}")
                return
            log(f"[CAPTURE] Webcam opened id={cam_id}, freq={freq_ms}ms")
        elif cam_type == "ip":
            cam_ip = self.cfg["capture"].get("camera_ip")
            if not cam_ip:
                log("[CAPTURE] camera_ip not set for IP camera")
                return
            self.cam = cv2.VideoCapture(str(cam_ip))
            if not self.cam.isOpened():
                log(f"[CAPTURE] Unable to open IP camera at {cam_ip}")
                return
            log(f"[CAPTURE] IP camera opened at {cam_ip}, freq={freq_ms}ms")
        else:
            cam_serial = self.cfg["capture"].get("camera_serial")
            log(f"[CAPTURE] Unsupported camera_type={cam_type} (serial={cam_serial})")
            return

        period = max(0.001, freq_ms / 1000.0)
        next_t = time.perf_counter()

        idx = 0
        while not stop_evt.is_set():
            ret, frame = self.cam.read()
            if not ret or frame is None:
                log("[CAPTURE] Frame non valido (ret=False)")
            else:
                idx += 1
                ts = time.strftime("%Y%m%d_%H%M%S")
                fname = f"frame_{idx:06d}_{ts}.{self.image_format}"
                self._save_image(frame, dest_dir / fname)

            next_t += period
            sleep = next_t - time.perf_counter()
            if sleep > 0:
                time.sleep(sleep)

        self.cam.release()
        log("[CAPTURE] Camera rilasciata")

class TestCapture(BaseCapture):
    def __init__(self, cfg: dict):
        super().__init__(cfg)
        self.src = Path(cfg["capture"].get("test_source_dir", "test_images"))

    def capture_loop(self, dest_dir: Path, freq_ms: int, stop_evt, log: Callable[[str], None]):
        imgs = sorted([p for p in self.src.glob("*") if p.is_file()])
        if not imgs:
            log(f"[CAPTURE] Nessuna immagine in {self.src}")
            return

        period = max(0.001, freq_ms / 1000.0)
        next_t = time.perf_counter()

        idx = 0
        pos = 0
        stop_on_exhausted = bool(self.cfg["capture"].get("stop_on_test_exhausted", False))

        log(f"[CAPTURE] Test mode: copying from {self.src}, freq={freq_ms}ms, stop_on_exhausted={stop_on_exhausted}")

        while not stop_evt.is_set():
            src_img = imgs[pos]
            pos += 1
            if pos >= len(imgs):
                if stop_on_exhausted:
                    log("[CAPTURE] test images exhausted -> stop session")
                    break
                pos = 0  # ricomincia

            idx += 1
            ts = time.strftime("%Y%m%d_%H%M%S")
            fname = f"frame_{idx:06d}_{ts}.{self.image_format}"
            dst = dest_dir / fname

            try:
                shutil.copy2(src_img, dst)
            except Exception as e:
                log(f"[CAPTURE] copy error: {e}")

            next_t += period
            sleep = next_t - time.perf_counter()
            if sleep > 0:
                time.sleep(sleep)

        log("[CAPTURE] Test mode: loop terminato")
