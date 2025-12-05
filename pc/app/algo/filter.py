# pc/app/algo/filter.py
import numpy as np
import cv2 as cv
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from .detect import MarkerDetection
from .pnp import MarkerPose

@dataclass
class FilterStats:
    discarded: List[int]
    corrected: List[int]

class MarkerFilter:
    def __init__(self, active: bool = True, min_flip_interval: float = 0.2):
        self.active = active
        self.min_flip_interval = min_flip_interval
        self._history: Dict[int, dict] = {} # id -> {z: float, ts: float}

    def apply(self, detections: List[MarkerDetection], poses: List[MarkerPose], timestamp: float) -> Tuple[List[MarkerDetection], List[MarkerPose], FilterStats]:
        if not self.active or timestamp is None:
            return detections, poses, FilterStats([], [])

        out_dets = []
        out_poses = []
        discarded = []
        corrected = []

        for det, pose in zip(detections, poses):
            z_current = pose.tvec.flatten()[2]
            
            # Recupera stato precedente
            prev = self._history.get(det.id)
            keep = True
            
            if prev:
                z_prev = prev['z']
                # Se il segno di Z cambia improvvisamente (flip)
                if z_prev * z_current < 0:
                    dt = timestamp - prev['ts']
                    if dt < self.min_flip_interval:
                        # Flip troppo veloce -> è un errore di ambiguità di OpenCV
                        # Strategia: Scartiamo il frame o Invertiamo la Z
                        # Qui scartiamo per sicurezza
                        keep = False
                        discarded.append(det.id)
            
            if keep:
                self._history[det.id] = {'z': z_current, 'ts': timestamp}
                out_dets.append(det)
                out_poses.append(pose)

        return out_dets, out_poses, FilterStats(discarded, corrected)