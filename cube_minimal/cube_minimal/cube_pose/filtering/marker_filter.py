"""Stateful filtering of marker poses between frames."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..aruco_detect import MarkerDetection
from ..marker_pose import MarkerPose


@dataclass
class MarkerHistory:
    """Track the last accepted state for a marker id."""

    z: float
    timestamp: Optional[float] = None
    area_px: Optional[float] = None


@dataclass
class MarkerFilterResult:
    """Result of filtering markers for a single frame."""

    accepted: List[Tuple[MarkerDetection, MarkerPose]]
    discarded_ids: List[int]
    corrected_ids: List[int]


class MarkerFilter:
    """Filter to reject or adjust unstable marker pose estimates."""

    def __init__(
        self,
        *,
        active: bool,
        try_adjust: bool,
        area_threshold_px: Optional[float] = None,
    ) -> None:
        self.active = bool(active)
        self.try_adjust = bool(try_adjust)
        self.area_threshold_px = (
            float(area_threshold_px) if area_threshold_px is not None else None
        )
        self._state: Dict[int, MarkerHistory] = {}

    def reset(self) -> None:
        """Clear all stored marker state."""

        self._state.clear()

    def apply(
        self,
        detections: Sequence[MarkerDetection],
        poses: Sequence[MarkerPose],
        timestamp: Optional[float] = None,
    ) -> MarkerFilterResult:
        """Filter marker poses for a frame, returning accepted entries."""

        accepted: List[Tuple[MarkerDetection, MarkerPose]] = []
        discarded: List[int] = []
        corrected: List[int] = []

        for det, pose in zip(detections, poses):
            marker_id = pose.id
            tvec = np.asarray(pose.tvec, dtype=float).reshape(3)
            z_val = float(tvec[2])
            area_val = getattr(det, "area", None)
            if area_val is not None:
                area_val = float(area_val)

            if self.active:
                history = self._state.get(marker_id)
                if history is None:
                    if (
                        self.area_threshold_px is not None
                        and area_val is not None
                        and area_val < self.area_threshold_px
                    ):
                        discarded.append(marker_id)
                        continue
                else:
                    prev_z = history.z
                    if (
                        abs(prev_z) > 1e-9
                        and abs(z_val) > 1e-9
                        and prev_z * z_val < 0.0
                    ):
                        if self.try_adjust:
                            corrected_pose = MarkerPose(
                                marker_id,
                                pose.rvec.copy(),
                                pose.tvec.copy(),
                                pose.R.copy(),
                            )
                            corrected_pose.tvec[2, 0] = -corrected_pose.tvec[2, 0]
                            accepted.append((det, corrected_pose))
                            corrected.append(marker_id)
                            self._state[marker_id] = MarkerHistory(
                                z=float(corrected_pose.tvec.reshape(3)[2]),
                                timestamp=timestamp,
                                area_px=area_val,
                            )
                            continue
                        discarded.append(marker_id)
                        continue

            accepted.append((det, pose))
            self._state[marker_id] = MarkerHistory(
                z=z_val,
                timestamp=timestamp,
                area_px=area_val,
            )

        return MarkerFilterResult(accepted, discarded, corrected)
