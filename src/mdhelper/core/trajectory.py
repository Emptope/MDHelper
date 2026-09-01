"""Backend-independent streaming trajectory port."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

from .system import Atom, Frame, FrameRange

TOPOLOGY_SUFFIXES = (".tpr", ".gro")
TRAJECTORY_SUFFIXES = (".xtc", ".trr", ".gro")


class TrajectorySource(Protocol):
    @property
    def atoms(self) -> tuple[Atom, ...]: ...

    @property
    def backend_name(self) -> str: ...

    @property
    def backend_display_name(self) -> str: ...

    @property
    def n_frames(self) -> int | None: ...

    @property
    def topology_path(self) -> Path: ...

    @property
    def trajectory_path(self) -> Path: ...

    def iter_frames(self, frame_range: FrameRange) -> Iterator[Frame]: ...

    def close(self) -> None: ...
