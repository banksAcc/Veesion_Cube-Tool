from typing import Tuple
import numpy as np

def load_camera(npz_path: str) -> Tuple[np.ndarray, np.ndarray]:
    """
    Carica intrinseci e distorsioni da un file .npz.

    Attese nel .npz una delle coppie chiave:
      - ('K', 'dist')  oppure
      - ('cameraMatrix', 'distCoeffs')

    Returns:
        K: (3,3) float64
        dist: (N,) o (1,N) float64
    Raises:
        ValueError se chiavi mancanti o file non valido.
    """
    D = np.load(npz_path)
    K = D.get("K", D.get("cameraMatrix", None))
    dist = D.get("dist", D.get("distCoeffs", None))
    if K is None or dist is None:
        raise ValueError(
            "Nel .npz devono esserci 'K' (o 'cameraMatrix') e 'dist' (o 'distCoeffs')."
        )
    return K.astype(float), dist.astype(float)
