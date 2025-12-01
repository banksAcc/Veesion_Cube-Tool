"""Utilities for detecting ArUco markers in an image."""

from dataclasses import dataclass
from typing import List, Tuple
import numpy as np
import cv2 as cv

# Supported dictionary names
DICT_MAP = {
    "4X4_50": cv.aruco.DICT_4X4_50,
    "4X4_100": cv.aruco.DICT_4X4_100,
    "5X5_50": cv.aruco.DICT_5X5_50,
    "6X6_50": cv.aruco.DICT_6X6_50,
    "7X7_50": cv.aruco.DICT_7X7_50,
    "APRILTAG_36h11": cv.aruco.DICT_APRILTAG_36h11,
}

def _contour_area(points: np.ndarray) -> float:
    pts = points.reshape(-1, 2)
    if pts.shape[0] < 3:
        return 0.0
    x = pts[:, 0]
    y = pts[:, 1]
    return float(0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


@dataclass
class MarkerDetection:
    """Basic detection result for a marker."""

    id: int
    corners: np.ndarray  # (4,2) float32, order: tl, tr, br, bl
    area_px: float | None = None

    def __post_init__(self) -> None:
        if self.area_px is None:
            self.area_px = _contour_area(self.corners.astype(np.float32))


def make_detector(dict_name: str) -> cv.aruco.ArucoDetector:
    """Create an ArUco detector from the dictionary name."""
    try:
        d = cv.aruco.getPredefinedDictionary(DICT_MAP[dict_name])
    except KeyError as exc:
        valid = ", ".join(sorted(DICT_MAP.keys()))
        raise ValueError(f"Unknown dictionary '{dict_name}'. Valid options: {valid}") from exc
    p = cv.aruco.DetectorParameters()
    return cv.aruco.ArucoDetector(d, p)


def detect_markers(img_bgr: np.ndarray, dict_name: str) -> List[MarkerDetection]:
    """Run ArUco detection on a BGR image.

    Returns
    -------
    List[MarkerDetection]
        Marker detections in detection order.

    Example
    -------
    ```python
    img = cv.imread("frame.png")
    detections = detect_markers(img, "4X4_50")
    print([m.id for m in detections])
    ```
    """

    det = make_detector(dict_name)
    gray = cv.cvtColor(img_bgr, cv.COLOR_BGR2GRAY)
    corners, ids, _ = det.detectMarkers(gray)
    out: List[MarkerDetection] = []
    if ids is None:
        return out
    for i, mid in enumerate(ids.flatten()):
        pts = corners[i].reshape(4, 2).astype(np.float32)
        area = _contour_area(pts)
        out.append(MarkerDetection(int(mid), pts, area))
    return out
