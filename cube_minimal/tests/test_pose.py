import sys
from pathlib import Path

import numpy as np
import cv2 as cv

# Make cube_minimal/src importable
sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from cube_pose.aruco_detect import MarkerDetection
from cube_pose.marker_pose import estimate_marker_poses, MarkerPose
from cube_pose.cube_pose import estimate_cube_pose


def test_estimate_marker_poses_identity():
    marker_size = 0.1
    K = np.array([[800, 0, 320], [0, 800, 240], [0, 0, 1]], dtype=np.float32)
    dist = np.zeros(5)

    h = marker_size / 2
    objp = np.array([
        [-h, h, 0],
        [h, h, 0],
        [h, -h, 0],
        [-h, -h, 0],
    ], dtype=np.float32)

    rvec_gt = np.zeros((3, 1), dtype=np.float32)
    tvec_gt = np.array([[0], [0], [1]], dtype=np.float32)
    imgp, _ = cv.projectPoints(objp, rvec_gt, tvec_gt, K, dist)
    corners = imgp.reshape(4, 2).astype(np.float32)

    det = MarkerDetection(1, corners)
    poses = estimate_marker_poses([det], K, dist, marker_size)

    assert len(poses) == 1
    pose = poses[0]
    assert pose.id == 1
    assert np.allclose(pose.rvec, rvec_gt, atol=1e-4)
    assert np.allclose(pose.tvec, tvec_gt, atol=1e-4)
    assert np.allclose(pose.R, np.eye(3), atol=1e-4)


def test_estimate_cube_pose_two_markers():
    cube_size = 0.1

    R1 = np.eye(3)
    rvec1, _ = cv.Rodrigues(R1)
    t1 = np.array([[0], [0], [cube_size / 2]])
    m1 = MarkerPose(0, rvec1, t1, R1)

    R2 = np.array([[0, 0, 1], [0, 1, 0], [-1, 0, 0]], dtype=float)
    rvec2, _ = cv.Rodrigues(R2)
    t2 = np.array([[cube_size / 2], [0], [0]])
    m2 = MarkerPose(1, rvec2, t2, R2)

    cube = estimate_cube_pose([m1, m2], cube_size)

    expected_R = np.array([
        [-1, 0, 0],
        [0, 1, 0],
        [0, 0, -1],
    ], dtype=float)
    assert np.allclose(cube.R, expected_R, atol=1e-6)
    assert np.allclose(cube.t, np.zeros(3), atol=1e-6)
