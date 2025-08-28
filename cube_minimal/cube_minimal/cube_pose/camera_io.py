from typing import Tuple
import numpy as np


def load_camera(npz_path: str) -> Tuple[np.ndarray, np.ndarray]:
    """Load intrinsics and distortion from a ``.npz`` file.

    The archive is expected to contain either ``("K", "dist")`` or
    ``("cameraMatrix", "distCoeffs")``.

    Returns
    -------
    Tuple[np.ndarray, np.ndarray]
        ``(K, dist)`` where ``K`` is ``(3,3)`` and ``dist`` is ``(N,)`` or
        ``(1,N)`` of type ``float64``.

    Raises
    ------
    ValueError
        If the required keys are missing or the file is invalid.

    Example
    -------
    ```python
    K, dist = load_camera("calib_data.npz")
    ```
    """

    D = np.load(npz_path)
    K = D.get("K", D.get("cameraMatrix", None))
    dist = D.get("dist", D.get("distCoeffs", None))
    if K is None or dist is None:
        raise ValueError(
            "The .npz must contain 'K' (or 'cameraMatrix') and 'dist' (or 'distCoeffs')."
        )
    return K.astype(float), dist.astype(float)
