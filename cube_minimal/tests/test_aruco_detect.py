import pytest
import cv2 as cv

from cube_minimal.cube_pose.aruco_detect import DICT_MAP, make_detector


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
