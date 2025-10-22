"""Typed payloads exchanged between application components."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional, TypeAlias, Union

from stream import FramePacket


@dataclass(frozen=True)
class BleMessage:
    """Representation of a message sent to the BLE device."""

    text: str

    def as_bytes(self) -> bytes:
        """Return the encoded payload expected by ``ble_client``."""

        return self.text.encode()


BLE_COMPUTATION_START = BleMessage("COMPUTATION START")
BLE_COMPUTATION_END = BleMessage("COMPUTATION END")


@dataclass(frozen=True)
class PoseStartMessage:
    """Payload emitted when a capture session starts."""

    session_key: str
    session_dir: Path
    frame_queue: asyncio.Queue[Optional[FramePacket]]
    start: str
    freq_ms: int
    label: str
    save_frames: bool
    save_dir: Optional[Path] = None
    action: Literal["start"] = "start"


@dataclass(frozen=True)
class PoseEndMessage:
    """Payload emitted once a capture session finishes."""

    session_key: str
    session_dir: Path
    start: str
    end: str
    freq_ms: int
    label: str
    save_dir: Optional[Path] = None
    action: Literal["end"] = "end"


PoseWorkerPayload: TypeAlias = Union[PoseStartMessage, PoseEndMessage]

