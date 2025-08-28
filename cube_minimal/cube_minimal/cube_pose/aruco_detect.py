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

@dataclass
class MarkerDetection:
    """Basic detection result for a marker."""

    id: int
    corners: np.ndarray  # (4,2) float32, order: tl, tr, br, bl


def make_detector(dict_name: str) -> cv.aruco.ArucoDetector:
    """Create an ArUco detector from the dictionary name."""

    d = cv.aruco.getPredefinedDictionary(DICT_MAP[dict_name])
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
        out.append(MarkerDetection(int(mid), corners[i].reshape(4,2).astype(np.float32)))
    return out
