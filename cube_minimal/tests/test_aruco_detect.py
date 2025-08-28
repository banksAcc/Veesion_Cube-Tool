import sys
from pathlib import Path
import pytest
import cv2 as cv

# Add src directory to path for imports
sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from cube_pose.aruco_detect import make_detector, DICT_MAP


def test_make_detector_valid():
    det = make_detector("4X4_50")
    assert isinstance(det, cv.aruco.ArucoDetector)


def test_make_detector_invalid():
    with pytest.raises(ValueError) as excinfo:
        make_detector("INVALID")
    message = str(excinfo.value)
    assert "INVALID" in message
    for key in DICT_MAP:
        assert key in message
