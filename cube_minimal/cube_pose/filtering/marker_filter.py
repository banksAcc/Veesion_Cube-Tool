"""Filtering utilities for marker pose stability."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import cv2 as cv
import numpy as np

from ..aruco_detect import MarkerDetection
from ..marker_pose import MarkerPose


@dataclass
class _MarkerState:
    z: float
    timestamp: Optional[float]
    area_px: Optional[float]


@dataclass
class MarkerFilterResult:
    detections: List[MarkerDetection]
    poses: List[MarkerPose]
    discarded_ids: List[int]
    corrected_ids: List[int]


class MarkerFilter:
    """Keep track of markers across frames to filter unstable poses."""

    def __init__(
        self,
        active: bool = False,
        try_adjust: bool = False,
        area_threshold_px: float = 0.0,
        min_flip_interval_s: float = 0.0,
    ) -> None:
        self.active = bool(active)
        self.try_adjust = bool(try_adjust)
        self.area_threshold_px = float(area_threshold_px)
        self.min_flip_interval_s = float(min_flip_interval_s)
        self._state: Dict[int, _MarkerState] = {}

    def reset(self) -> None:
        self._state.clear()

    def apply(
        self,
        detections: Sequence[MarkerDetection],
        poses: Sequence[MarkerPose],
        timestamp: Optional[float] = None,
    ) -> MarkerFilterResult:
        if len(detections) != len(poses):
            raise ValueError("Detections and poses must have the same length.")

        if not self.active:
            used_det = list(detections)
            used_pose = list(poses)
            for det, pose in zip(used_det, used_pose):
                self._update_state(det, pose, timestamp)
            return MarkerFilterResult(used_det, used_pose, [], [])

        used_detections: List[MarkerDetection] = []
        used_poses: List[MarkerPose] = []
        discarded: List[int] = []
        corrected: List[int] = []

        for det, pose in zip(detections, poses):
            marker_id = det.id
            area = det.area_px
            prev = self._state.get(marker_id)

            keep = True
            adjusted_pose = pose
            if prev is None:
                if self.area_threshold_px > 0 and area is not None:
                    if area < self.area_threshold_px:
                        keep = False
                elif self.area_threshold_px > 0 and area is None:
                    # Unknown area -> keep the marker but note that we could not evaluate threshold.
                    keep = True
            else:
                prev_z = prev.z
                current_z = float(np.asarray(pose.tvec).reshape(-1)[2])
                if prev_z * current_z < 0:
                    flip_fast = self._flip_too_fast(prev.timestamp, timestamp)
                    if self.try_adjust and flip_fast:
                        adjusted_pose = self._flip_pose_z(pose)
                        corrected.append(marker_id)
                        current_z = -current_z
                    elif flip_fast or not self.try_adjust:
                        keep = False
                        pass

            if keep:
                if adjusted_pose is not pose:
                    used_poses.append(adjusted_pose)
                else:
                    used_poses.append(pose)
                used_detections.append(det)
                self._update_state(det, adjusted_pose, timestamp)
            else:
                discarded.append(marker_id)

        return MarkerFilterResult(used_detections, used_poses, discarded, corrected)

    def _update_state(
        self,
        detection: MarkerDetection,
        pose: MarkerPose,
        timestamp: Optional[float],
    ) -> None:
        z_value = float(np.asarray(pose.tvec).reshape(-1)[2])
        self._state[detection.id] = _MarkerState(z_value, timestamp, detection.area_px)

    @staticmethod
    def _flip_pose_z(pose: MarkerPose) -> MarkerPose:
        new_tvec = np.asarray(pose.tvec, dtype=float).copy()
        new_tvec = new_tvec.reshape(-1)
        new_tvec[2] = -new_tvec[2]
        flipped_tvec = new_tvec.reshape(pose.tvec.shape)
        flip_matrix = np.diag([1.0, -1.0, -1.0])
        flipped_R = pose.R @ flip_matrix
        flipped_rvec, _ = cv.Rodrigues(flipped_R)
        return MarkerPose(pose.id, flipped_rvec, flipped_tvec, flipped_R)

    def _flip_too_fast(
        self, prev_timestamp: Optional[float], current_timestamp: Optional[float]
    ) -> bool:
        if self.min_flip_interval_s <= 0:
            return False
        if prev_timestamp is None or current_timestamp is None:
            return False
        delta = current_timestamp - prev_timestamp
        if delta < 0:
            return False
        return delta < self.min_flip_interval_s
