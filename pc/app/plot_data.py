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


def load_tvecs(session_path: Path) -> np.ndarray:
    """Return an Nx3 array with translation vectors from a capture session."""
    if not session_path.exists():
        raise FileNotFoundError(session_path)

    data = json.loads(session_path.read_text(encoding="utf-8"))
    frames: Iterable[dict] = data.get("frames", [])

    tvecs: List[Sequence[float]] = []
    for frame in frames:
        if not frame.get("ok"):
            continue
        tvec = frame.get("tvec_tip")
        if not tvec or len(tvec) != 3:
            continue
        tvecs.append(tvec)

    if not tvecs:
        raise ValueError(f"No valid translation vectors found in {session_path}")

    return np.asarray(tvecs, dtype=float)


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
    args = parser.parse_args()

    config_path = args.config
    config = load_config(config_path)

    session_path = resolve_session_path(args.session_file, config, config_path)
    tvecs = load_tvecs(session_path)

    title = args.title or f"Capture trajectory - {session_path.stem}"
    plot_trajectory(tvecs, title)


if __name__ == "__main__":
    main()
