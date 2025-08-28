"""Capture backends for the PC application.

This module provides a small hierarchy of capture strategies:

* :class:`BaseCapture` defines helpers for persisting frames to disk using the
  format configured in ``config.yaml``.
* :class:`CameraCapture` grabs frames from a physical camera through OpenCV's
  :class:`~cv2.VideoCapture`. The backend works with a generic UVC webcam and
  is ready for Basler ``pypylon`` integration once available.
* :class:`PylonCapture` uses Basler's ``pypylon`` SDK when available.
* :class:`TestCapture` emulates acquisition by copying images from a directory,
  allowing deterministic runs without any camera.

``SessionManager`` (see :mod:`session_manager`) chooses between
``CameraCapture`` and ``TestCapture`` based on the ``capture.use_camera`` flag
in the configuration file.
"""

import random
import shutil
import time
from pathlib import Path
from typing import Callable, Optional

try:
    import cv2
except Exception:  # pragma: no cover - optional dependency
    cv2 = None

try:
    from pypylon import pylon
except Exception:  # pragma: no cover - optional dependency
    pylon = None


class BaseCapture:
    """Common image saving helpers for capture implementations."""

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
        """Persist an image frame to disk using the configured format."""

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
    """Capture images from a real camera using OpenCV's VideoCapture."""

    def __init__(self, cfg: dict):
        """Create a camera capturer."""

        super().__init__(cfg)
        self.cam = None

    def capture_loop(
        self,
        dest_dir: Path,
        freq_ms: int,
        stop_evt,
        log: Callable[[str, str], None],
    ):
        if cv2 is None:
            log("OpenCV not available: cannot use camera", "error")
            return

        cam_id = int(self.cfg["capture"].get("camera_id", 0))
        self.cam = cv2.VideoCapture(cam_id)
        if not self.cam.isOpened():
            log(f"Failed to open camera id={cam_id}", "error")
            return

        log(f"Camera opened id={cam_id}, freq={freq_ms}ms", "info")
        period = max(0.001, freq_ms / 1000.0)
        next_t = time.perf_counter()

        idx = 0
        while not stop_evt.is_set():
            ret, frame = self.cam.read()
            if not ret or frame is None:
                log("Invalid frame (ret=False)", "warning")
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
        log("Camera released", "info")


class PylonCapture(BaseCapture):
    """Capture backend using Basler's pypylon SDK."""

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        self.cam: Optional["pylon.InstantCamera"] = None
        self.converter: Optional["pylon.ImageFormatConverter"] = None

    def _open_camera(self, log: Callable[[str, str], None]):
        if pylon is None:
            raise RuntimeError("pypylon not available")

        factory = pylon.TlFactory.GetInstance()
        serial = self.cfg["capture"].get("camera_serial")
        ip = self.cfg["capture"].get("camera_ip")

        if serial:
            serial = str(serial)
            for dev in factory.EnumerateDevices():
                if dev.GetSerialNumber() == serial:
                    self.cam = pylon.InstantCamera(factory.CreateDevice(dev))
                    break
            if self.cam is None:
                raise RuntimeError(f"No camera with serial {serial}")
        elif ip:
            di = pylon.DeviceInfo()
            di.SetIpAddress(str(ip))
            self.cam = pylon.InstantCamera(factory.CreateDevice(di))
        else:
            self.cam = pylon.InstantCamera(factory.CreateFirstDevice())

        self.cam.Open()
        self.converter = pylon.ImageFormatConverter()
        self.converter.OutputPixelFormat = pylon.PixelType_BGR8packed
        self.converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned

    def capture_loop(
        self,
        dest_dir: Path,
        freq_ms: int,
        stop_evt,
        log: Callable[[str, str], None],
    ):
        try:
            self._open_camera(log)
        except Exception as e:  # pragma: no cover - hardware dependent
            log(f"Pylon open failed: {e}", "error")
            return

        log("Pylon camera opened", "info")
        self.cam.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)

        period = max(0.001, freq_ms / 1000.0)
        next_t = time.perf_counter()
        idx = 0

        while not stop_evt.is_set() and self.cam.IsGrabbing():
            grab = self.cam.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)
            if grab.GrabSucceeded():
                img = self.converter.Convert(grab)
                frame = img.GetArray()
                idx += 1
                ts = time.strftime("%Y%m%d_%H%M%S")
                fname = f"frame_{idx:06d}_{ts}.{self.image_format}"
                try:
                    self._save_image(frame, dest_dir / fname)
                except Exception as e:  # pragma: no cover - hardware dependent
                    log(f"Save error: {e}", "error")
            else:
                log("Grab failed", "warning")
            grab.Release()

            next_t += period
            sleep = next_t - time.perf_counter()
            if sleep > 0:
                time.sleep(sleep)

        self.cam.StopGrabbing()
        self.cam.Close()
        log("Pylon camera released", "info")


class TestCapture(BaseCapture):
    """Simulated capture that replays a directory of still images.

    Images are copied to the destination folder at the configured frequency.
    The files are iterated sequentially or shuffled if ``shuffle_test_images``
    is enabled. When the sequence is exhausted the loop restarts, unless
    ``stop_on_test_exhausted`` is true.
    """

    def __init__(self, cfg: dict):
        """Create a test image capturer."""

        super().__init__(cfg)
        self.src = Path(cfg["capture"].get("test_source_dir", "test_images"))
        self.shuffle = bool(cfg["capture"].get("shuffle_test_images", False))

    def capture_loop(
        self,
        dest_dir: Path,
        freq_ms: int,
        stop_evt,
        log: Callable[[str, str], None],
    ):
        imgs = sorted([p for p in self.src.glob("*") if p.is_file()])
        if not imgs:
            log(f"No images in {self.src}", "error")
            return

        if self.shuffle:
            random.shuffle(imgs)
            log("Test mode: shuffled source images", "info")

        period = max(0.001, freq_ms / 1000.0)
        next_t = time.perf_counter()

        idx = 0
        pos = 0
        stop_on_exhausted = bool(self.cfg["capture"].get("stop_on_test_exhausted", False))

        log(
            f"Test mode: copying from {self.src}, freq={freq_ms}ms, stop_on_exhausted={stop_on_exhausted}",
            "info",
        )

        while not stop_evt.is_set():
            src_img = imgs[pos]
            pos += 1
            if pos >= len(imgs):
                if stop_on_exhausted:
                    log("test images exhausted -> stop session", "info")
                    break
                pos = 0  # restart from beginning

            idx += 1
            ts = time.strftime("%Y%m%d_%H%M%S")
            fname = f"frame_{idx:06d}_{ts}.{self.image_format}"
            dst = dest_dir / fname

            log(f"Copying {src_img.name} -> {fname}", "info")
            try:
                shutil.copy2(src_img, dst)
            except Exception as e:
                log(f"copy error: {e}", "error")

            next_t += period
            sleep = next_t - time.perf_counter()
            if sleep > 0:
                time.sleep(sleep)

        log("Test mode: loop finished", "info")

