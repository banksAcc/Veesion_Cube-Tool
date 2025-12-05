# pc/app/algo/data_loader.py
import json
import numpy as np
from pathlib import Path
from typing import Tuple, Dict

def load_camera_calibration(npz_path: str) -> Tuple[np.ndarray, np.ndarray]:
    """Carica K (CameraMatrix) e dist (DistCoeffs) da un file .npz."""
    path = Path(npz_path)
    if not path.exists():
        raise FileNotFoundError(f"Calibration file not found: {path}")

    with np.load(path) as data:
        K = data.get("K", data.get("cameraMatrix", None))
        dist = data.get("dist", data.get("distCoeffs", None))
    
    if K is None or dist is None:
        raise ValueError("File .npz invalido: mancano 'cameraMatrix' o 'distCoeffs'.")
    
    return K.astype(float), dist.astype(float)

def load_ico_transforms(json_path: str) -> Dict[str, np.ndarray]:
    """Carica il dizionario delle trasformazioni Faccia -> Corpo."""
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"Transforms JSON not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Converte le liste in numpy array
    return {k: np.asarray(v, dtype=float) for k, v in data.items()}