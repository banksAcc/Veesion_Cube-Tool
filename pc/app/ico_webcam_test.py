"""Quick webcam test runner for the truncated icosahedron pose estimator.

This utility bypasses the BLE/session machinery and runs the ``ico`` pose
pipeline directly on frames grabbed from a local webcam. It reads the same
``config.yaml`` used by the main app to pick calibration and marker settings,
then displays live overlays along with the current pose.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Optional

import yaml

# --- MODIFICA 1: Import dalla nuova struttura algo ---
from algo import (
    estimate_truncated_ico_from_image, 
    load_camera_calibration, 
    load_ico_transforms
)
from algo.filter import MarkerFilter

from config_models import AppConfig

try:
    import cv2  # type: ignore[import]
    import numpy as np  # type: ignore[import]
except Exception:  # pragma: no cover - optional dependency
    cv2 = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]


DEFAULT_CFG = Path("config.yaml")


def _load_config(path: Path) -> AppConfig:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return AppConfig.from_mapping(data)


def _build_marker_filter(cfg: AppConfig) -> MarkerFilter:
    mcfg = cfg.pose.ico.marker_filter
    # Nota: Il nuovo MarkerFilter supporta principalmente active e min_flip_interval
    return MarkerFilter(
        active=bool(mcfg.active_marker_filter),
        min_flip_interval=float(mcfg.min_flip_interval_s or 0.2),
    )


def _format_vec(vec: np.ndarray) -> str:
    flat = np.asarray(vec, dtype=float).reshape(-1)
    return ", ".join(f"{x: .3f}" for x in flat)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CFG, help="config.yaml path")
    parser.add_argument("--camera-id", type=int, default=None, help="override capture.camera_id")
    parser.add_argument("--no-overlay", action="store_true", help="do not draw overlay, only text")
    args = parser.parse_args()

    if cv2 is None or np is None:
        print("OpenCV with contrib modules is required for this test", file=sys.stderr)
        return 2

    cfg = _load_config(args.config)
    
    # --- MODIFICA 2: Caricamento risorse UNA TANTUM (Prima del loop) ---
    calib_path = cfg.pose.camera_calibration_npz
    if calib_path is None or not Path(calib_path).exists():
        print(f"Camera calibration file not found: {calib_path}", file=sys.stderr)
        return 2
    
    # Caricamento K e Dist
    try:
        K, dist = load_camera_calibration(str(calib_path))
        print(f"Calibration loaded from: {calib_path}")
    except Exception as e:
        print(f"Error loading calibration: {e}", file=sys.stderr)
        return 2

    # Caricamento Trasformazioni Faccia->Corpo
    transform_path: Optional[Path] = cfg.pose.ico.transform_file
    try:
        if transform_path and Path(transform_path).exists():
            transforms = load_ico_transforms(str(transform_path))
            print(f"Transforms loaded from: {transform_path}")
        else:
            # Se vuoi gestire il fallback integrato nel package, dovresti gestirlo in data_loader
            # Per ora assumiamo che il file debba esistere
            print(f"Transforms file missing: {transform_path}", file=sys.stderr)
            return 2
    except Exception as e:
        print(f"Error loading transforms: {e}", file=sys.stderr)
        return 2

    # Configurazione Camera
    camera_id = args.camera_id if args.camera_id is not None else cfg.capture.camera_id
    print(f"Opening camera id={camera_id} ...")
    cap = cv2.VideoCapture(int(camera_id))
    if not cap.isOpened():
        print(f"Failed to open camera id={camera_id}", file=sys.stderr)
        return 2

    marker_filter = _build_marker_filter(cfg)
    marker_size_m = float(cfg.pose.ico.marker_size_mm) / 1000.0
    dictionary = cfg.pose.ico.dictionary

    print("Press 'q' to quit.")
    
    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                print("Frame grab failed, exiting")
                break

            try:
                # --- MODIFICA 3: Chiamata Ottimizzata ---
                # Passiamo K, dist e transforms (oggetti in memoria) invece dei path
                result = estimate_truncated_ico_from_image(
                    image=frame,
                    K=K,
                    dist=dist,
                    transforms=transforms,
                    aruco_dict=dictionary,
                    marker_size=marker_size_m,
                    return_overlay=not args.no_overlay,
                    marker_filter=marker_filter,
                    timestamp=time.time(),
                )
            except ValueError:
                # Nessun marker o errore di logica (es. facce non riconosciute)
                overlay = frame
                text = "No markers detected"
                cv2.putText(
                    overlay, text, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 
                    1.0, (0, 0, 255), 2, cv2.LINE_AA
                )
                cv2.imshow("ico pose", overlay)
            except Exception as exc:
                # Errori imprevisti
                overlay = frame
                text = f"Error: {exc}"[:70]
                cv2.putText(
                    overlay, text, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 
                    1.0, (0, 0, 255), 2, cv2.LINE_AA
                )
                cv2.imshow("ico pose", overlay)
                # print(exc) # Scommenta per debug profondo
            else:
                # Successo
                overlay = result.get("overlay") if not args.no_overlay else frame
                if overlay is None:
                    overlay = frame
                
                rvec = result.get("rvec")
                tvec = result.get("tvec")
                
                info_lines = [
                    f"Markers: {result.get('num_markers', 0)}",
                ]
                
                if rvec is not None:
                    info_lines.append(f"rvec: {_format_vec(rvec)}")
                if tvec is not None:
                    # Calcola distanza euclidea
                    dist_val = np.linalg.norm(tvec)
                    info_lines.append(f"tvec: {_format_vec(tvec)} | D: {dist_val:.2f}m")

                y = 30
                for line in info_lines:
                    cv2.putText(
                        overlay, line, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 
                        0.6, (0, 255, 0), 2, cv2.LINE_AA
                    )
                    y += 25
                cv2.imshow("ico pose", overlay)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())