"""High level API to estimate the pose of a cube from a single image."""

from typing import Dict, Any, Union, Optional
import numpy as np
import cv2 as cv

from .camera_io import load_camera
from .aruco_detect import detect_markers
from .marker_pose import estimate_marker_poses
from .cube_pose import estimate_cube_pose
from .filtering import MarkerFilter


def estimate_cube_from_image(
    image_or_path: Union[str, np.ndarray],
    camera_npz: str,
    aruco_dict: str,
    marker_size: float,
    cube_size: float,
    pair_strategy: str = "first",
    return_overlay: bool = False,
    marker_filter: Optional[MarkerFilter] = None,
    frame_timestamp: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Estimate the cube pose from a single image.

    Parameters
    ----------
    image_or_path:
        Path to an image or a BGR array of shape ``(H, W, 3)``.
    camera_npz:
        Path to a ``.npz`` file containing camera intrinsics (``K`` or
        ``cameraMatrix``) and distortion coefficients (``dist`` or
        ``distCoeffs``).
    aruco_dict:
        Name of the ArUco dictionary (e.g. ``"4X4_50"``).
    marker_size:
        Side length of the marker in meters (only the black square).
    cube_size:
        Side length of the cube in meters.
    pair_strategy:
        ``"first"`` uses the first two detected markers, ``"max_angle"``
        selects the pair with the most orthogonal normals.
    return_overlay:
        If ``True`` an image with diagnostic overlay is also returned.
    marker_filter:
        Optional :class:`~cube_minimal.cube_pose.filtering.MarkerFilter` instance
        used to discard or adjust marker poses before estimating the cube pose.
    frame_timestamp:
        Optional timestamp (in seconds) associated with the frame, forwarded to
        ``marker_filter`` when provided.

    Returns
    -------
    Dict[str, Any]
        Dictionary with keys:

        - ``"tvec"``: ``(3,)`` cube centre in the camera frame (meters)
        - ``"rvec"``: ``(3,1)`` Rodrigues vector of the cube
        - ``"R"``: ``(3,3)`` rotation matrix of the cube
        - ``"quat"``: ``(4,)`` quaternion ``(w, x, y, z)``
        - ``"num_markers"``: number of markers used
        - ``"markers"``: list of marker poses used (id, rvec, tvec, R, area)
        - ``"discarded_marker_ids"``: marker ids removed by the filter
        - ``"corrected_marker_ids"``: marker ids adjusted by the filter
        - ``"overlay"``: optional BGR image if ``return_overlay`` is ``True``

    Raises
    ------
    FileNotFoundError
        If ``image_or_path`` is a string and the image cannot be read.
    ValueError
        If ``image_or_path`` is not a valid BGR array or no markers are detected.

    Example
    -------
    ```python
    from cube_minimal.cube_pose import estimate_cube_from_image
    result = estimate_cube_from_image(
        "frame.tiff", "calib.npz", "4X4_50", 0.055, 0.060
    )
    print(result["tvec"])
    ```
    """
    # Load image
    if isinstance(image_or_path, str):
        img = cv.imread(image_or_path)
        if img is None:
            raise FileNotFoundError(f"Unable to read image: {image_or_path}")
    else:
        img = image_or_path
        if (
            img is None
            or not isinstance(img, np.ndarray)
            or img.ndim != 3
            or img.shape[2] != 3
        ):
            raise ValueError("image_or_path must be a path or BGR np.ndarray (H,W,3).")

    # Camera
    K, dist = load_camera(camera_npz)

    # Detection
    detections = detect_markers(img, aruco_dict)
    if len(detections) == 0:
        raise ValueError("No markers detected in the image.")

    # Marker poses
    poses = estimate_marker_poses(detections, K, dist, marker_size)

    # Cube pose
    filter_result = None
    if marker_filter is not None:
        filter_result = marker_filter.apply(detections, poses, timestamp=frame_timestamp)
        poses = [mp for _, mp in filter_result.accepted]
        detections = [det for det, _ in filter_result.accepted]
        if len(poses) == 0:
            raise ValueError("No markers remaining after filtering.")

    cube = estimate_cube_pose(poses, cube_size, pair_strategy=pair_strategy)

    marker_dicts: list[dict[str, Any]] = []
    for det, mp in zip(detections, poses):
        marker_dicts.append(
            {
                "id": int(mp.id),
                "rvec": mp.rvec.reshape(3).tolist(),
                "tvec": mp.tvec.reshape(3).tolist(),
                "R": mp.R.tolist(),
                "area": float(getattr(det, "area", 0.0)),
            }
        )

    # Optional overlay
    overlay = None
    if return_overlay:
        from .viz import draw_marker_outline, draw_small_axes, draw_wirecube, project_points_camframe

        overlay = img.copy()
        # axes + outline for each marker
        for det, mp in zip(detections, poses):
            draw_marker_outline(overlay, det.corners, (0, 255, 255), 2)
            cv2_len = max(marker_size * 0.5, cube_size * 0.3)  # rough scale
            draw_small_axes(overlay, K, dist, mp.rvec, mp.tvec, cv2_len)
        # cube wireframe
        draw_wirecube(
            overlay,
            K,
            dist,
            cube.rvec,
            cube.t,
            cube_size,
            color=(0, 255, 0),
            thickness=2,
        )

    return {
        "tvec": cube.t,
        "rvec": cube.rvec,
        "R": cube.R,
        "quat": cube.quat,
        "num_markers": len(poses),
        "markers": marker_dicts,
        "discarded_marker_ids": [] if filter_result is None else filter_result.discarded_ids,
        "corrected_marker_ids": [] if filter_result is None else filter_result.corrected_ids,
        "overlay": overlay,
    }
