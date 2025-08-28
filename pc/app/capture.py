"""Image capture helpers used by the session manager.

The module provides a base class and two implementations: one that captures
frames from a physical camera and another that copies pre-existing images for
testing purposes.
"""

import shutil
import time
from pathlib import Path
from typing import Callable, Optional

try:
    import cv2
except Exception:
    cv2 = None


class BaseCapture:
    """Base class for capture implementations."""

    def __init__(self, cfg: dict):
        """Initialize capture settings from configuration.

        Args:
            cfg (dict): Application configuration.

        Side Effects:
            None.
        """

        self.cfg = cfg
        self.image_format = cfg["capture"].get("image_format", "jpg").lower()
        self.jpeg_quality = int(cfg["capture"].get("jpeg_quality", 90))

    def _save_image(self, frame, path: Path):
        """Persist an image frame to disk.

        Args:
            frame: Image data to save.
            path (Path): Destination path.

        Side Effects:
            Writes the image file to ``path``.
        """

        if frame is None:
            raise RuntimeError("Frame is None - cannot save")

        fmt = self.image_format
        if fmt in ("png",):
            ok = cv2.imwrite(str(path), frame)
        elif fmt in ("tif", "tiff"):
            # optional: compression from config
            comp_map = {"none": 1, "lzw": 2, "packbits": 3, "deflate": 4}
            comp_name = str(self.cfg["capture"].get("tiff_compression", "none")).lower()
            comp = comp_map.get(comp_name, 1)
            ok = cv2.imwrite(str(path), frame, [int(cv2.IMWRITE_TIFF_COMPRESSION), comp])
        else:
            ok = cv2.imwrite(str(path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality])

        if not ok:
            raise RuntimeError(f"Failed to write image: {path}")


class CameraCapture(BaseCapture):
    """Capture frames from an attached camera using OpenCV."""

    def __init__(self, cfg: dict):
        """Create a camera capturer.

        Args:
            cfg (dict): Application configuration.

        Side Effects:
            None.
        """

        super().__init__(cfg)
        self.cam = None

    def capture_loop(self, dest_dir: Path, freq_ms: int, stop_evt, log: Callable[[str], None]):
        """Continuously capture frames until ``stop_evt`` is set.

        Args:
            dest_dir (Path): Directory where images are saved.
            freq_ms (int): Capture period in milliseconds.
            stop_evt: Threading event used to stop the loop.
            log (Callable[[str], None]): Logging function.

        Side Effects:
            Creates image files in ``dest_dir`` and logs progress.
        """

        if cv2 is None:
            log("[CAPTURE] OpenCV not available: cannot use the camera")
            return

        cam_id = int(self.cfg["capture"].get("camera_id", 0))
        self.cam = cv2.VideoCapture(cam_id)
        if not self.cam.isOpened():
            log(f"[CAPTURE] Cannot open camera id={cam_id}")
            return

        log(f"[CAPTURE] Camera opened id={cam_id}, freq={freq_ms}ms")
        period = max(0.001, freq_ms / 1000.0)
        next_t = time.perf_counter()

        idx = 0
        while not stop_evt.is_set():
            ret, frame = self.cam.read()
            if not ret or frame is None:
                log("[CAPTURE] Invalid frame (ret=False)")
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
        log("[CAPTURE] Camera released")


class TestCapture(BaseCapture):
    """Capture frames by copying images from a source directory."""

    def __init__(self, cfg: dict):
        """Create a test image capturer.

        Args:
            cfg (dict): Application configuration.

        Side Effects:
            None.
        """

        super().__init__(cfg)
        self.src = Path(cfg["capture"].get("test_source_dir", "test_images"))

    def capture_loop(self, dest_dir: Path, freq_ms: int, stop_evt, log: Callable[[str], None]):
        """Copy images into ``dest_dir`` to simulate camera capture.

        Args:
            dest_dir (Path): Destination directory for copied images.
            freq_ms (int): Interval between copies in milliseconds.
            stop_evt: Event flag to stop the loop.
            log (Callable[[str], None]): Logging function.

        Side Effects:
            Copies files and logs progress.
        """

        imgs = sorted([p for p in self.src.glob("*") if p.is_file()])
        if not imgs:
            log(f"[CAPTURE] No images in {self.src}")
            return

        period = max(0.001, freq_ms / 1000.0)
        next_t = time.perf_counter()

        idx = 0
        pos = 0
        stop_on_exhausted = bool(self.cfg["capture"].get("stop_on_test_exhausted", False))

        log(
            f"[CAPTURE] Test mode: copying from {self.src}, freq={freq_ms}ms, "
            f"stop_on_exhausted={stop_on_exhausted}"
        )

        while not stop_evt.is_set():
            src_img = imgs[pos]
            pos += 1
            if pos >= len(imgs):
                if stop_on_exhausted:
                    log("[CAPTURE] test images exhausted -> stop session")
                    break
                pos = 0  # restart

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

        log("[CAPTURE] Test mode: loop ended")
