"""Utilities for streaming capture frames between threads and asyncio tasks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np


@dataclass
class FramePacket:
    """Container holding a single captured frame and associated metadata."""

    session_key: str
    index: int
    timestamp: float
    frame: "np.ndarray"
    filename: str
    save_path: Optional[Path] = None

    @property
    def iso_timestamp(self) -> str:
        """Return the capture timestamp encoded as an ISO string."""

        return datetime.fromtimestamp(self.timestamp).isoformat()

