"""Visualization helpers for drawing markers and cubes."""

from typing import Iterable
import numpy as np
import cv2 as cv


def draw_marker_outline(img: np.ndarray, corners: np.ndarray,
                        color=(0,255,255), thickness: int = 2) -> None:
    """Draw the perimeter of a marker given its ``(4,2)`` corner array.

    Example
    -------
    ```python
    draw_marker_outline(img, detection.corners)
    ```
    """

    c = corners.reshape(4,2).astype(int)
    for a,b in [(0,1),(1,2),(2,3),(3,0)]:
        cv.line(img, tuple(c[a]), tuple(c[b]), color, thickness)


def draw_small_axes(img: np.ndarray, K: np.ndarray, dist: np.ndarray,
                    rvec: np.ndarray, tvec: np.ndarray, axis_len: float) -> None:
    """Draw local axes (X=red, Y=green, Z=blue) of length ``axis_len``.

    Example
    -------
    ```python
    draw_small_axes(img, K, dist, rvec, tvec, 0.03)
    ```
    """

    cv.drawFrameAxes(img, K, dist, rvec, tvec, axis_len, 2)


def project_points_camframe(K: np.ndarray, dist: np.ndarray,
                            pts_cam: np.ndarray) -> np.ndarray:
    """Project 3D points expressed in the camera frame."""

    r0 = np.zeros((3,1), float)
    t0 = np.zeros((3,1), float)
    pts2d, _ = cv.projectPoints(np.asarray(pts_cam, float).reshape(-1,3), r0, t0, K, dist)
    return pts2d.reshape(-1,2)


def draw_wirecube(img: np.ndarray, K: np.ndarray, dist: np.ndarray,
                  rvec: np.ndarray, tvec: np.ndarray,
                  cube_size: float, color=(0,255,0), thickness: int=2) -> None:
    """Draw a wireframe cube centred at ``tvec`` and oriented by ``rvec``.

    Example
    -------
    ```python
    draw_wirecube(img, K, dist, rvec, tvec, 0.06)
    ```
    """

    h = cube_size * 0.5
    pts = np.array(
        [[-h,-h,-h],[ h,-h,-h],[ h, h,-h],[-h, h,-h],
         [-h,-h, h],[ h,-h, h],[ h, h, h],[-h, h, h]],
        dtype=float
    )
    edges = [(0,1),(1,2),(2,3),(3,0),
             (4,5),(5,6),(6,7),(7,4),
             (0,4),(1,5),(2,6),(3,7)]
    uv, _ = cv.projectPoints(pts, rvec, tvec, K, dist)
    uv = uv.reshape(-1,2).astype(int)
    for a,b in edges:
        cv.line(img, tuple(uv[a]), tuple(uv[b]), color, thickness)
