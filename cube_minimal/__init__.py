"""Minimal cube pose estimation utilities.

This package provides helper functions to detect ArUco markers and estimate
the pose of either a cube or a truncated icosahedron observed by a calibrated
camera.

Example
-------
```python
from cube_minimal.cube_pose.api import estimate_cube_from_image

result = estimate_cube_from_image(
    image_or_path="frame.tiff",
    camera_npz="calib_data.npz",
    aruco_dict="4X4_50",
    marker_size=0.055,
    cube_size=0.060,
)
print(result["tvec"])
```
"""

from .cube_pose.api import estimate_cube_from_image
from .ico_pose.api import estimate_truncated_ico_from_image

__all__ = ["estimate_cube_from_image", "estimate_truncated_ico_from_image"]
