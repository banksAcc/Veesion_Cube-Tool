import numpy as np
import pytest

from cube_pose.api import estimate_cube_from_image


def test_nonexistent_image_path_raises():
    with pytest.raises(FileNotFoundError):
        estimate_cube_from_image(
            "nonexistent_image.jpg",
            "dummy_camera.npz",
            "4X4_50",
            0.02,
            0.05,
        )


def test_invalid_array_raises_value_error():
    invalid_img = np.zeros((10, 10, 4), dtype=np.float32)
    with pytest.raises(ValueError):
        estimate_cube_from_image(
            invalid_img,
            "dummy_camera.npz",
            "4X4_50",
            0.02,
            0.05,
        )

