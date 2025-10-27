"""Typed representations of the YAML application configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Optional


def _as_mapping(raw: Any) -> Mapping[str, Any]:
    """Return a mapping view for ``raw`` falling back to an empty dict."""

    if isinstance(raw, Mapping):
        return raw
    return {}


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y", "on"}:
            return True
        if lowered in {"false", "0", "no", "n", "off"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class BleConfig:
    """Configuration for BLE discovery and connection."""

    name_prefix: str = "ESP32-RGB-BLE"
    addr: Optional[str] = None
    scan_timeout: float = 8.0

    @classmethod
    def from_mapping(cls, raw: Any) -> "BleConfig":
        data = _as_mapping(raw)
        return cls(
            name_prefix=str(data.get("name_prefix", cls.name_prefix)),
            addr=data.get("addr") or None,
            scan_timeout=_coerce_float(data.get("scan_timeout"), cls.scan_timeout),
        )


@dataclass(frozen=True)
class CaptureConfig:
    """Configuration for frame acquisition and persistence."""

    frequency_ms: int = 200
    output_root: Path = Path("../captures")
    save_frames: bool = False
    frame_queue_size: int = 4
    simulate_camera: bool = False
    camera_type: str = "pylon"
    camera_id: int = 0
    camera_serial: Optional[str] = None
    camera_ip: Optional[str] = None
    keep_camera_warm: bool = True
    test_source_dir: Path = Path("../image_to_be_used")

    @classmethod
    def from_mapping(cls, raw: Any) -> "CaptureConfig":
        data = _as_mapping(raw)
        output_root = Path(data.get("output_root", cls.output_root))
        test_source_dir = Path(data.get("test_source_dir", cls.test_source_dir))
        camera_serial = data.get("camera_serial")
        camera_ip = data.get("camera_ip")
        return cls(
            frequency_ms=_coerce_int(data.get("frequency_ms"), cls.frequency_ms),
            output_root=output_root,
            save_frames=_coerce_bool(data.get("save_frames"), cls.save_frames),
            frame_queue_size=_coerce_int(data.get("frame_queue_size"), cls.frame_queue_size),
            simulate_camera=_coerce_bool(data.get("simulate_camera"), cls.simulate_camera),
            camera_type=str(data.get("camera_type", cls.camera_type)),
            camera_id=_coerce_int(data.get("camera_id"), cls.camera_id),
            camera_serial=str(camera_serial) if camera_serial is not None else None,
            camera_ip=str(camera_ip) if camera_ip is not None else None,
            keep_camera_warm=_coerce_bool(data.get("keep_camera_warm"), cls.keep_camera_warm),
            test_source_dir=test_source_dir,
        )


@dataclass(frozen=True)
class MarkerFilterConfig:
    """Configuration for the optional ArUco marker filter."""

    active_marker_filter: bool = False
    try_adj_marker: bool = False
    area_threshold_px: float = 0.0

    @classmethod
    def from_mapping(cls, raw: Any) -> "MarkerFilterConfig":
        data = _as_mapping(raw)
        return cls(
            active_marker_filter=_coerce_bool(
                data.get("active_marker_filter"), cls.active_marker_filter
            ),
            try_adj_marker=_coerce_bool(data.get("try_adj_marker"), cls.try_adj_marker),
            area_threshold_px=_coerce_float(
                data.get("area_threshold_px"), cls.area_threshold_px
            ),
        )


@dataclass(frozen=True)
class CubePoseConfig:
    """Configuration specific to the default cube pose estimation backend."""

    dictionary: str = "4X4_50"
    marker_size_mm: float = 55.0
    cube_size_mm: float = 60.0
    pair_strategy: str = "first"
    wand_offset_m: float = 0.0
    wand_directions: Mapping[int, Any] = field(default_factory=dict)
    marker_filter: MarkerFilterConfig = field(default_factory=MarkerFilterConfig)

    @classmethod
    def from_mapping(cls, raw: Any) -> "CubePoseConfig":
        data = _as_mapping(raw)
        directions_raw = _as_mapping(data.get("wand_directions", {}))
        wand_directions: dict[int, Any] = {}
        for key, value in directions_raw.items():
            try:
                wand_directions[int(key)] = value
            except (TypeError, ValueError):
                continue
        return cls(
            dictionary=str(data.get("dictionary", cls.dictionary)),
            marker_size_mm=_coerce_float(data.get("marker_size_mm"), cls.marker_size_mm),
            cube_size_mm=_coerce_float(data.get("cube_size_mm"), cls.cube_size_mm),
            pair_strategy=str(data.get("pair_strategy", cls.pair_strategy)),
            wand_offset_m=_coerce_float(data.get("wand_offset_m"), cls.wand_offset_m),
            wand_directions=wand_directions,
            marker_filter=MarkerFilterConfig.from_mapping(data.get("marker_filter", {})),
        )


@dataclass(frozen=True)
class PoseConfig:
    """Configuration for the pose worker."""

    enabled: bool = True
    method: str = "cube"
    max_parallel_jobs: int = 1
    cube: CubePoseConfig = field(default_factory=CubePoseConfig)
    camera_calibration_npz: Optional[Path] = None
    save_overlay: bool = True

    @classmethod
    def from_mapping(cls, raw: Any) -> "PoseConfig":
        data = _as_mapping(raw)
        calibration = data.get("camera_calibration_npz")
        return cls(
            enabled=_coerce_bool(data.get("enabled"), cls.enabled),
            method=str(data.get("method", cls.method)),
            max_parallel_jobs=_coerce_int(
                data.get("max_parallel_jobs"), cls.max_parallel_jobs
            ),
            cube=CubePoseConfig.from_mapping(data.get("cube", {})),
            camera_calibration_npz=Path(calibration) if calibration else None,
            save_overlay=_coerce_bool(data.get("save_overlay"), cls.save_overlay),
        )


@dataclass(frozen=True)
class RuntimeConfig:
    """Generic runtime flags that influence logging and debugging."""

    debug: bool = False
    log_level: str = "INFO"
    log_to_file: bool = False

    @classmethod
    def from_mapping(cls, raw: Any) -> "RuntimeConfig":
        data = _as_mapping(raw)
        return cls(
            debug=_coerce_bool(data.get("debug"), cls.debug),
            log_level=str(data.get("log_level", cls.log_level)),
            log_to_file=_coerce_bool(data.get("log_to_file"), cls.log_to_file),
        )


@dataclass(frozen=True)
class PlotConfig:
    """Configuration for optional plotting utilities."""

    default_pose_json: Optional[Path] = None

    @classmethod
    def from_mapping(cls, raw: Any) -> "PlotConfig":
        data = _as_mapping(raw)
        default_json = data.get("default_pose_json")
        return cls(default_pose_json=Path(default_json) if default_json else None)


@dataclass(frozen=True)
class AppConfig:
    """Aggregated application configuration with strongly-typed sections."""

    ble: BleConfig
    capture: CaptureConfig
    pose: PoseConfig
    runtime: RuntimeConfig
    plot: PlotConfig
    raw: MutableMapping[str, Any] = field(repr=False)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "AppConfig":
        return cls(
            ble=BleConfig.from_mapping(raw.get("ble", {})),
            capture=CaptureConfig.from_mapping(raw.get("capture", {})),
            pose=PoseConfig.from_mapping(raw.get("pose", {})),
            runtime=RuntimeConfig.from_mapping(raw.get("runtime", {})),
            plot=PlotConfig.from_mapping(raw.get("plot", {})),
            raw=dict(raw),
        )

    def as_dict(self) -> dict[str, Any]:
        """Return a mutable mapping compatible with legacy helpers."""

        return dict(self.raw)

