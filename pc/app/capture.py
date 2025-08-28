"""Capture backends for the PC application.

This module provides a small hierarchy of capture strategies:

* :class:`BaseCapture` defines helpers for persisting frames to disk using the
  format configured in ``config.yaml``.
* :class:`CameraCapture` grabs frames from a physical camera through OpenCV's
  :class:`~cv2.VideoCapture`.  The backend works with a generic UVC webcam and
  is ready for Basler ``pypylon`` integration once available.
* :class:`TestCapture` emulates acquisition by copying images from a directory,
  allowing deterministic runs without any camera.

``SessionManager`` (see :mod:`session_manager`) chooses between
``CameraCapture`` and ``TestCapture`` based on the ``capture.use_camera`` flag
in the configuration file.
"""

import shutil
import time
import random
from pathlib import Path
from typing import Callable, Optional

try:
    import cv2
except Exception:
    cv2 = None

try:
    from pypylon import pylon
except Exception:  # pragma: no cover - optional dependency
    pylon = None

class BaseCapture:
    """Common image saving helpers for capture implementations."""

    def __init__(self, cfg: dict):
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
        super().__init__(cfg)
        self.cam = None

    def capture_loop(self, dest_dir: Path, freq_ms: int, stop_evt, log: Callable[[str], None]):
        """Continuously grab frames from a camera and save them to *dest_dir*.

        Works with generic webcams and industrial cameras such as Basler
        when the appropriate drivers are installed.
        """
        if cv2 is None:
            log("[CAPTURE] OpenCV not available: cannot use camera")
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



class PylonCapture(BaseCapture):
    """Capture backend using Basler's pypylon SDK."""

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        self.cam: Optional["pylon.InstantCamera"] = None
        self.converter: Optional["pylon.ImageFormatConverter"] = None

    def _open_camera(self, log: Callable[[str], None]):
        if pylon is None:
            raise RuntimeError("pypylon non disponibile")

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
                raise RuntimeError(f"Nessuna camera con serial {serial}")
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

    def capture_loop(self, dest_dir: Path, freq_ms: int, stop_evt, log: Callable[[str], None]):
        try:
            self._open_camera(log)
        except Exception as e:
            log(f"[CAPTURE] pylon open failed: {e}")
            return

        log("[CAPTURE] Pylon camera aperta")
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
                except Exception as e:
                    log(f"[CAPTURE] save error: {e}")
            else:
                log("[CAPTURE] grab fallita")
            grab.Release()

            next_t += period
            sleep = next_t - time.perf_counter()
            if sleep > 0:
                time.sleep(sleep)

        self.cam.StopGrabbing()
        self.cam.Close()
        log("[CAPTURE] Pylon camera rilasciata")

class TestCapture(BaseCapture):
    """Simulated capture that replays a directory of still images.

    Images are copied to the destination folder at the configured frequency.
    The files are iterated sequentially or shuffled if ``shuffle_test_images``
    is enabled. When the sequence is exhausted the loop restarts, unless
    ``stop_on_test_exhausted`` is true.
    """

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        self.src = Path(cfg["capture"].get("test_source_dir", "test_images"))
        self.shuffle = bool(cfg["capture"].get("shuffle_test_images", False))

    def capture_loop(self, dest_dir: Path, freq_ms: int, stop_evt, log: Callable[[str], None]):
        """Copy images from the source directory into *dest_dir* at the given rate."""
        imgs = sorted([p for p in self.src.glob("*") if p.is_file()])
        if not imgs:
            log(f"[CAPTURE] No images found in {self.src}")
            return

        if self.shuffle:
            random.shuffle(imgs)
            log("[CAPTURE] Test mode: shuffled source images")

        period = max(0.001, freq_ms / 1000.0)
        next_t = time.perf_counter()

        idx = 0
        pos = 0
        stop_on_exhausted = bool(self.cfg["capture"].get("stop_on_test_exhausted", False))

        log(
            f"[CAPTURE] Test mode: copying from {self.src}, freq={freq_ms}ms, "
            f"stop_on_exhausted={stop_on_exhausted}, shuffle={self.shuffle}"
        )

        while not stop_evt.is_set():
            src_img = imgs[pos]
            pos += 1
            if pos >= len(imgs):
                if stop_on_exhausted:
                    log("[CAPTURE] Test images exhausted -> stop session")
                    break
                if self.shuffle:
                    random.shuffle(imgs)
                    log("[CAPTURE] Test images exhausted -> reshuffle and restart sequence")
                else:
                    log("[CAPTURE] Test images exhausted -> restart sequence")
                pos = 0  # restart sequence
            idx += 1
            ts = time.strftime("%Y%m%d_%H%M%S")
            fname = f"frame_{idx:06d}_{ts}.{self.image_format}"
            dst = dest_dir / fname

            log(f"[CAPTURE] Copying {src_img.name} -> {fname}")
            try:
                shutil.copy2(src_img, dst)
            except Exception as e:
                log(f"[CAPTURE] copy error: {e}")

            next_t += period
            sleep = next_t - time.perf_counter()
            if sleep > 0:
                time.sleep(sleep)

        log("[CAPTURE] Test mode: loop terminated")
