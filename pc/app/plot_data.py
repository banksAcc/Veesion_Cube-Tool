"""Plot capture session translation vectors in 3D with a reference plane."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable, List, Sequence


import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import numpy as np
import yaml

DEFAULT_CONFIG_NAME = "config.yaml"
OVERLAY_SUFFIX = "_overlay"


def load_config(config_path: Path) -> dict[str, Any]:
    """Load YAML configuration data."""
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("Configuration root must be a mapping")
    return config


def resolve_session_path(
    session_arg: Path | None,
    config: dict[str, Any],
    config_path: Path,
) -> Path:
    """Return the pose JSON path either from CLI or config."""
    if session_arg is not None:
        return session_arg

    plot_cfg = config.get("plot")
    if not isinstance(plot_cfg, dict):
        raise ValueError("Missing 'plot' section in configuration")

    default_pose = plot_cfg.get("default_pose_json")
    if not default_pose:
        raise ValueError("Missing 'default_pose_json' in configuration plot section")

    path = Path(default_pose)
    if not path.is_absolute():
        path = (config_path.parent / path).resolve()
    return path


def load_session_data(session_path: Path) -> dict[str, Any]:
    """Load pose session JSON data."""
    if not session_path.exists():
        raise FileNotFoundError(session_path)

    data = json.loads(session_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Session file must contain a JSON object: {session_path}")
    return data


def load_tvecs(session_data: dict[str, Any], session_path: Path) -> np.ndarray:
    """Return an Nx3 array with translation vectors from a capture session."""

    frames: Iterable[dict] = session_data.get("frames", [])

    tvecs: List[Sequence[float]] = []
    for frame in frames:
        if not frame.get("ok"):
            continue
        if "tip_pose" in frame and isinstance(frame["tip_pose"], Sequence):
            pose = frame["tip_pose"]
            if len(pose) >= 3:
                tvecs.append(pose[:3])
                continue
        tvec = frame.get("tvec_tip") or frame.get("tvec")
        if not tvec or len(tvec) < 3:
            continue
        tvecs.append(tvec[:3])

    if not tvecs:
        raise ValueError(f"No valid translation vectors found in {session_path}")

    return np.asarray(tvecs, dtype=float)


def infer_session_directory(session_file: Path) -> Path:
    """Return the directory that contains raw/overlay frames for a session JSON."""

    stem = session_file.stem
    if stem.endswith("_pose"):
        stem = stem[: -len("_pose")]
    return session_file.with_name(stem)


def overlay_path_for_frame(session_file: Path, frame_name: str) -> Path:
    """Return the overlay file path for a given frame name using the *_overlay convention."""

    session_dir = infer_session_directory(session_file)
    frame_path = session_dir / frame_name
    return frame_path.with_name(f"{frame_path.stem}{OVERLAY_SUFFIX}{frame_path.suffix}")


def first_overlay_pair(
    session_file: Path, session_data: dict[str, Any]
) -> tuple[Path, Path] | None:
    """Return the first pair of (raw, overlay) paths, if available."""

    frames = session_data.get("frames")
    if not isinstance(frames, list):
        return None

    session_dir = infer_session_directory(session_file)
    for frame in frames:
        if not isinstance(frame, dict):
            continue
        filename = frame.get("file")
        if not filename:
            continue
        raw_path = session_dir / filename
        overlay_name = frame.get("overlay_file")
        if overlay_name:
            overlay_path = session_dir / overlay_name
        else:
            overlay_path = overlay_path_for_frame(session_file, filename)
        return raw_path, overlay_path
    return None


def plot_trajectory(tvecs: np.ndarray, title: str) -> None:
    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection="3d")

    xs, ys, zs = tvecs[:, 0], tvecs[:, 1], tvecs[:, 2]
    steps = np.arange(len(tvecs))

    line, = ax.plot(xs, ys, zs, color="steelblue", linewidth=1.6, label="trajectory")
    scatter = ax.scatter(xs, ys, zs, c=steps, cmap="viridis", s=45, depthshade=True)
    fig.colorbar(scatter, ax=ax, shrink=0.7, pad=0.02, label="frame index")

    x_min, x_max = xs.min(), xs.max()
    y_min, y_max = ys.min(), ys.max()
    palne_z = 0.85
    z_min = min(zs.min(), palne_z)
    z_max = max(zs.max(), palne_z)

    x_span = x_max - x_min
    y_span = y_max - y_min
    z_span = z_max - z_min
    pad = max(max(x_span, y_span, z_span), 1e-3) * 0.1

    x_span_vals = np.linspace(x_min - pad, x_max + pad, 10)
    y_span_vals = np.linspace(y_min - pad, y_max + pad, 10)
    X, Y = np.meshgrid(x_span_vals, y_span_vals)
    #Z = np.zeros_like(X)
    Z = np.full_like(X, 0.85)

    ax.plot_surface(X, Y, Z, alpha=0.18, color="gray", edgecolor="none")

    ax.set_xlim(x_min - pad, x_max + pad)
    ax.set_ylim(y_min - pad, y_max + pad)
    ax.set_zlim(z_min - pad, z_max + pad)
    ax.set_box_aspect((
        max(x_span, 1e-3) + 2 * pad,
        max(y_span, 1e-3) + 2 * pad,
        max(z_span, 1e-3) + 2 * pad,
    ))

    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.set_zlabel("Z")
    ax.set_title(title)
    ax.view_init(elev=25, azim=-60)
    ax.legend(handles=[line], loc="upper right")

    fig.subplots_adjust(left=0.0, right=1.0, bottom=0.0, top=1.0)
    plt.show()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "session_file",
        nargs="?",
        type=Path,
        help="Path to the *_pose.json file produced by a capture session",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).with_name(DEFAULT_CONFIG_NAME),
        help="Config YAML path (defaults to config.yaml beside this script)",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="Custom title for the 3D plot",
    )
    parser.add_argument(
        "--print-overlay",
        action="store_true",
        help="Print the raw/overlay paths for manual TIFF checks",
    )
    args = parser.parse_args()

    config_path = args.config
    config = load_config(config_path)

    session_path = resolve_session_path(args.session_file, config, config_path)
    session_data = load_session_data(session_path)
    tvecs = load_tvecs(session_data, session_path)

    if args.print_overlay:
        pair = first_overlay_pair(session_path, session_data)
        if pair is None:
            print("No frame entries with overlay information were found.")
        else:
            raw_path, overlay_path = pair
            print(
                f"First raw frame path: {raw_path} (exists: {raw_path.exists()})"
            )
            print(
                f"Overlay path ({OVERLAY_SUFFIX}): {overlay_path} (exists: {overlay_path.exists()})"
            )

    title = args.title or f"Capture trajectory - {session_path.stem}"
    plot_trajectory(tvecs, title)


if __name__ == "__main__":
    main()
