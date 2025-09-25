"""Capture backends for the PC application.

This module provides a hierarchy of capture strategies:

* :class:`BaseCapture` defines the template for opening, running and closing a
  capture backend while offering helpers for saving frames.
* :class:`OpenCvCapture` grabs frames from a physical camera through OpenCV's
  :class:`~cv2.VideoCapture`.
* :class:`PylonCapture` uses Basler's ``pypylon`` SDK when available.
* :class:`TestCapture` emulates acquisition by copying images from a directory,
  allowing deterministic runs without any camera.

``SessionManager`` (see :mod:`session_manager`) chooses between
``OpenCvCapture`` and ``TestCapture`` based on the ``capture.use_camera`` flag
in the configuration file.
"""

import random
import shutil
import time
from abc import ABC, abstractmethod
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


class BaseCapture(ABC):
    """Abstract capture backend with helpers for persistence and timing."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        capture_cfg = cfg.get("capture", {})
        self.image_format = capture_cfg.get("image_format", "jpg").lower()
        self.jpeg_quality = int(capture_cfg.get("jpeg_quality", 90))
        self._is_open = False
        self.auto_close = True

    def set_auto_close(self, auto_close: bool) -> None:
        """Control whether :meth:`capture_loop` closes the backend automatically."""

        self.auto_close = bool(auto_close)

    def open(self, log: Callable[[str, str], None]) -> None:
        """Open underlying resources if not already open."""

        if self._is_open:
            return
        self._open_backend(log)
        self._is_open = True

    def close(self, log: Callable[[str, str], None]) -> None:
        """Close underlying resources if open."""

        if not self._is_open:
            return
        try:
            self._close_backend(log)
        finally:
            self._is_open = False

    def capture_loop(
        self,
        dest_dir: Path,
        freq_ms: int,
        stop_evt,
        log: Callable[[str, str], None],
    ) -> None:
        """Template loop used by concrete capture implementations."""

        try:
            self.open(log)
        except Exception as exc:  # pragma: no cover - hardware dependent
            log(f"Capture open failed: {exc}", "error")
            self.close(log)
            return

        period = max(0.001, freq_ms / 1000.0)
        next_t = time.perf_counter()
        idx = 0

        try:
            self._on_loop_start(dest_dir, freq_ms, log)
            while not stop_evt.is_set():
                try:
                    frame = self._grab_frame(log)
                except StopIteration:
                    self._on_source_exhausted(log)
                    break
                except Exception as exc:  # pragma: no cover - hardware dependent
                    log(f"Capture grab error: {exc}", "error")
                    break

                if frame is None:
                    self._handle_empty_frame(log)
                else:
                    idx += 1
                    fname = self._generate_filename(idx)
                    dst = dest_dir / fname
                    try:
                        self._persist_frame(frame, dst, log)
                    except Exception as exc:
                        log(f"Persist error: {exc}", "error")

                next_t += period
                sleep = next_t - time.perf_counter()
                if sleep > 0:
                    time.sleep(sleep)
        finally:
            self._on_loop_end(log)
            if self.auto_close:
                self.close(log)

    def _generate_filename(self, idx: int) -> str:
        ts = time.strftime("%Y%m%d_%H%M%S")
        return f"frame_{idx:06d}_{ts}.{self.image_format}"

    def _persist_frame(self, frame, path: Path, _log: Callable[[str, str], None]) -> None:
        """Persist an image frame to disk using the configured format."""

        if cv2 is None:
            raise RuntimeError("OpenCV not available: cannot persist frames")
        self._save_image(frame, path)

    def _handle_empty_frame(self, log: Callable[[str, str], None]) -> None:
        log("Empty frame received", "warning")

    def _on_source_exhausted(self, log: Callable[[str, str], None]) -> None:
        log("Capture source exhausted", "info")

    def _on_loop_start(
        self, dest_dir: Path, freq_ms: int, log: Callable[[str, str], None]
    ) -> None:  # pragma: no cover - hook
        """Hook executed once before entering the capture loop."""

    def _on_loop_end(self, log: Callable[[str, str], None]) -> None:  # pragma: no cover - hook
        """Hook executed once after exiting the capture loop."""

    @abstractmethod
    def _open_backend(self, log: Callable[[str, str], None]) -> None:
        """Open concrete backend resources."""

    @abstractmethod
    def _grab_frame(self, log: Callable[[str, str], None]):
        """Return next frame or raise StopIteration if exhausted."""

    @abstractmethod
    def _close_backend(self, log: Callable[[str, str], None]) -> None:
        """Release concrete backend resources."""

    def _save_image(self, frame, path: Path) -> None:
        if frame is None:
            raise RuntimeError("Frame is None - cannot save")

        fmt = self.image_format
        if fmt in ("png",):
            ok = cv2.imwrite(str(path), frame)
        elif fmt in ("tif", "tiff"):
            comp_map = {
                "none": 1,
                "lzw": 5,
                "deflate": 8,
                "packbits": 32773,
            }
            comp_name = str(self.cfg["capture"].get("tiff_compression", "none")).lower()
            comp = comp_map.get(comp_name, 1)
            ok = cv2.imwrite(
                str(path),
                frame,
                [int(cv2.IMWRITE_TIFF_COMPRESSION), int(comp)],
            )
        else:
            ok = cv2.imwrite(
                str(path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality]
            )

        if not ok:
            raise RuntimeError(f"Failed to write image: {path}")


class OpenCvCapture(BaseCapture):
    """Capture images from a real camera using OpenCV's VideoCapture."""

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        self.cam = None
        self.camera_id = int(self.cfg["capture"].get("camera_id", 0))

    def _open_backend(self, log: Callable[[str, str], None]) -> None:
        if cv2 is None:
            raise RuntimeError("OpenCV not available: cannot use camera")

        self.cam = cv2.VideoCapture(self.camera_id)
        if not self.cam.isOpened():
            raise RuntimeError(f"Failed to open camera id={self.camera_id}")

        log(
            f"Camera opened id={self.camera_id}, freq={self.cfg['capture'].get('frequency_ms', 'n/a')}ms",
            "info",
        )

    def _grab_frame(self, log: Callable[[str, str], None]):
        if self.cam is None:
            raise RuntimeError("Camera not opened")
        ret, frame = self.cam.read()
        if not ret or frame is None:
            log("Invalid frame (ret=False)", "warning")
            return None
        return frame

    def _close_backend(self, log: Callable[[str, str], None]) -> None:
        if self.cam is not None:
            try:
                self.cam.release()
            finally:
                self.cam = None
        log("Camera released", "info")

    def _handle_empty_frame(self, _log: Callable[[str, str], None]) -> None:
        return


class PylonCapture(BaseCapture):
    """Capture backend using Basler's pypylon SDK."""

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        self.cam: Optional["pylon.InstantCamera"] = None
        self.converter: Optional["pylon.ImageFormatConverter"] = None
        self._grab_timeout_ms = int(self.cfg["capture"].get("pylon_grab_timeout_ms", 5000))

    def _open_backend(self, log: Callable[[str, str], None]) -> None:
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
        log("Pylon camera opened", "info")

    def _grab_frame(self, log: Callable[[str, str], None]):
        if self.cam is None or self.converter is None:
            raise RuntimeError("Pylon camera not opened")

        if not self.cam.IsGrabbing():
            raise RuntimeError("Pylon camera is not grabbing")

        grab = self.cam.RetrieveResult(
            self._grab_timeout_ms, pylon.TimeoutHandling_ThrowException
        )
        try:
            if not grab.GrabSucceeded():
                log("Grab failed", "warning")
                return None
            img = self.converter.Convert(grab)
            return img.GetArray()
        finally:
            grab.Release()

    def _close_backend(self, log: Callable[[str, str], None]) -> None:
        if self.cam is not None:
            try:
                if self.cam.IsGrabbing():
                    self.cam.StopGrabbing()
                self.cam.Close()
            finally:
                self.cam = None
                self.converter = None
        log("Pylon camera released", "info")

    def _handle_empty_frame(self, _log: Callable[[str, str], None]) -> None:
        return

    def _on_loop_start(
        self, dest_dir: Path, freq_ms: int, log: Callable[[str, str], None]
    ) -> None:
        if self.cam is not None and not self.cam.IsGrabbing():
            self.cam.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
            log("Pylon grabbing started", "info")

    def _on_loop_end(self, log: Callable[[str, str], None]) -> None:
        if self.cam is not None and self.cam.IsGrabbing():
            self.cam.StopGrabbing()
            log("Pylon grabbing stopped", "info")


class TestCapture(BaseCapture):
    """Simulated capture that replays a directory of still images."""

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        self.src = Path(self.cfg["capture"].get("test_source_dir", "test_images"))
        self.shuffle = bool(self.cfg["capture"].get("shuffle_test_images", False))
        self.stop_on_exhausted = bool(
            self.cfg["capture"].get("stop_on_test_exhausted", False)
        )
        self._imgs: list[Path] = []
        self._pos = 0

    def _open_backend(self, log: Callable[[str, str], None]) -> None:
        imgs = sorted([p for p in self.src.glob("*") if p.is_file()])
        if not imgs:
            raise RuntimeError(f"No images in {self.src}")

        if self.shuffle:
            random.shuffle(imgs)
            log("Test mode: shuffled source images", "info")

        self._imgs = imgs
        self._pos = 0

    def _grab_frame(self, log: Callable[[str, str], None]):
        if not self._imgs:
            raise RuntimeError("Test images not loaded")

        img = self._imgs[self._pos]
        self._pos += 1
        if self._pos >= len(self._imgs):
            if self.stop_on_exhausted:
                raise StopIteration
            self._pos = 0

        return img

    def _persist_frame(self, frame, path: Path, log: Callable[[str, str], None]) -> None:
        log(f"Copying {Path(frame).name} -> {path.name}", "info")
        shutil.copy2(frame, path)

    def _close_backend(self, log: Callable[[str, str], None]) -> None:
        self._imgs = []
        self._pos = 0
        log("Test mode: backend closed", "info")

    def _on_loop_start(
        self, dest_dir: Path, freq_ms: int, log: Callable[[str, str], None]
    ) -> None:
        log(
            f"Test mode: copying from {self.src}, freq={freq_ms}ms, stop_on_exhausted={self.stop_on_exhausted}",
            "info",
        )

    def _on_loop_end(self, log: Callable[[str, str], None]) -> None:
        log("Test mode: loop finished", "info")

    def _on_source_exhausted(self, log: Callable[[str, str], None]) -> None:
        log("test images exhausted -> stop session", "info")

