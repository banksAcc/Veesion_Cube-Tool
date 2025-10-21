import numpy as np

from cube_minimal.cube_pose.aruco_detect import MarkerDetection
from cube_minimal.cube_pose.filtering import MarkerFilter
from cube_minimal.cube_pose.marker_pose import MarkerPose


def _pose(z_value: float) -> MarkerPose:
    rvec = np.zeros((3, 1), dtype=float)
    tvec = np.array([[0.0], [0.0], [z_value]], dtype=float)
    R = np.eye(3, dtype=float)
    return MarkerPose(1, rvec, tvec, R)


def _detection(area: float) -> MarkerDetection:
    corners = np.array(
        [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]], dtype=np.float32
    )
    return MarkerDetection(1, corners, area)


def test_filter_discards_small_area_when_no_history():
    marker_filter = MarkerFilter(active=True, try_adjust=False, area_threshold_px=120.0)
    result = marker_filter.apply([_detection(50.0)], [_pose(0.2)], timestamp=0.0)
    assert result.accepted == []
    assert result.discarded_ids == [1]


def test_filter_accepts_flip_when_adjust_enabled():
    marker_filter = MarkerFilter(active=True, try_adjust=True)
    marker_filter.apply([_detection(200.0)], [_pose(0.2)], timestamp=0.0)
    result = marker_filter.apply([_detection(200.0)], [_pose(-0.2)], timestamp=0.1)
    assert len(result.accepted) == 1
    _, pose = result.accepted[0]
    assert pose.tvec[2, 0] > 0
    assert result.corrected_ids == [1]
    assert result.discarded_ids == []


def test_filter_discards_flip_without_adjust():
    marker_filter = MarkerFilter(active=True, try_adjust=False)
    marker_filter.apply([_detection(200.0)], [_pose(0.2)], timestamp=0.0)
    result = marker_filter.apply([_detection(200.0)], [_pose(-0.2)], timestamp=0.1)
    assert result.accepted == []
    assert result.discarded_ids == [1]
    assert result.corrected_ids == []
