import numpy as np
import pytest

from cube_minimal.cube_pose import api
from cube_minimal.cube_pose.aruco_detect import MarkerDetection
from cube_minimal.cube_pose.marker_pose import MarkerPose
from cube_minimal.cube_pose.filtering.marker_filter import MarkerFilter


def _make_pose(marker_id: int, z_value: float) -> MarkerPose:
    rvec = np.zeros((3, 1), dtype=float)
    tvec = np.array([[0.0], [0.0], [z_value]], dtype=float)
    R = np.eye(3, dtype=float)
    return MarkerPose(marker_id, rvec, tvec, R)


def _make_detection(marker_id: int, area: float) -> MarkerDetection:
    side = float(np.sqrt(area)) if area > 0 else 0.0
    corners = np.array(
        [
            [0.0, 0.0],
            [side, 0.0],
            [side, side],
            [0.0, side],
        ],
        dtype=np.float32,
    )
    return MarkerDetection(marker_id, corners)


def test_marker_filter_discards_small_area():
    marker_filter = MarkerFilter(active=True, try_adjust=False, area_threshold_px=1500.0)
    det = _make_detection(1, area=500.0)
    pose = _make_pose(1, z_value=0.2)

    result = marker_filter.apply([det], [pose])

    assert result.detections == []
    assert result.poses == []
    assert result.discarded_ids == [1]
    assert result.corrected_ids == []


def test_marker_filter_discards_flipped_without_adjustment():
    marker_filter = MarkerFilter(active=True, try_adjust=False)
    det1 = _make_detection(2, area=2000.0)
    pose1 = _make_pose(2, z_value=0.3)
    marker_filter.apply([det1], [pose1])

    det2 = _make_detection(2, area=2000.0)
    pose2 = _make_pose(2, z_value=-0.3)

    result = marker_filter.apply([det2], [pose2])

    assert result.detections == []
    assert result.poses == []
    assert result.discarded_ids == [2]
    assert result.corrected_ids == []


def test_marker_filter_adjusts_flipped_marker():
    marker_filter = MarkerFilter(active=True, try_adjust=True)
    det1 = _make_detection(3, area=2000.0)
    pose1 = _make_pose(3, z_value=0.25)
    marker_filter.apply([det1], [pose1])

    det2 = _make_detection(3, area=2000.0)
    pose2 = _make_pose(3, z_value=-0.25)

    result = marker_filter.apply([det2], [pose2])

    assert len(result.detections) == 1
    assert len(result.poses) == 1
    assert result.discarded_ids == []
    assert result.corrected_ids == [3]

    corrected_pose = result.poses[0]
    assert np.isclose(float(corrected_pose.tvec.reshape(-1)[2]), 0.25)


def test_estimate_cube_from_image_respects_filter(monkeypatch, tmp_path):
    calib_path = tmp_path / "camera.npz"
    np.savez(calib_path, K=np.eye(3), dist=np.zeros(5))

    area = 500.0
    corners = np.array(
        [
            [0.0, 0.0],
            [np.sqrt(area), 0.0],
            [np.sqrt(area), np.sqrt(area)],
            [0.0, np.sqrt(area)],
        ],
        dtype=np.float32,
    )

    def fake_detect(img, dict_name):
        return [MarkerDetection(10, corners)]

    def fake_estimate_marker_poses(dets, K, dist, size):
        return [_make_pose(10, z_value=0.2)]

    monkeypatch.setattr(api, "detect_markers", fake_detect)
    monkeypatch.setattr(api, "estimate_marker_poses", fake_estimate_marker_poses)

    marker_filter = MarkerFilter(active=True, try_adjust=False, area_threshold_px=1000.0)

    image = np.zeros((10, 10, 3), dtype=np.uint8)

    with pytest.raises(ValueError):
        api.estimate_cube_from_image(
            image,
            str(calib_path),
            "4X4_50",
            0.05,
            0.06,
            marker_filter=marker_filter,
        )
