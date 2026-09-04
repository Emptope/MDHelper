"""Simulation-system, atom, frame, and periodic-box domain contracts."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray

from .errors import InputError
from .species import SpeciesRoleSuggestion

Vec3 = tuple[float, float, float]
Coordinates = NDArray[np.float64]


@dataclass(frozen=True)
class Atom:
    index: int
    name: str
    element: str
    residue_name: str
    residue_id: int
    molecule_id: str
    charge_e: float | None = None


@dataclass(frozen=True)
class Box:
    """Periodic box vectors in nm, stored as row vectors a, b, c."""

    vectors_nm: tuple[Vec3, Vec3, Vec3]

    @property
    def volume_nm3(self) -> float:
        a, b, c = self.vectors_nm
        cross_bc = (
            b[1] * c[2] - b[2] * c[1],
            b[2] * c[0] - b[0] * c[2],
            b[0] * c[1] - b[1] * c[0],
        )
        return abs(a[0] * cross_bc[0] + a[1] * cross_bc[1] + a[2] * cross_bc[2])

    def validate(self) -> None:
        if not math.isfinite(self.volume_nm3) or self.volume_nm3 <= 1e-12:
            raise InputError(
                "The trajectory frame has no valid periodic box.",
                "RDF and cumulative RDF analyses require a non-zero three-dimensional box.",
            )


@dataclass(frozen=True)
class Frame:
    index: int
    time_ps: float
    positions_nm: Coordinates
    box: Box


@dataclass(frozen=True)
class FrameRange:
    start: int = 0
    stop: int | None = None
    stride: int = 1

    def validate(self) -> None:
        if type(self.start) is not int:
            raise InputError("start must be an integer.")
        if self.stop is not None and type(self.stop) is not int:
            raise InputError("stop must be an integer or null.")
        if type(self.stride) is not int:
            raise InputError("stride must be an integer.")
        if self.start < 0:
            raise InputError("start must be greater than or equal to zero.")
        if self.stop is not None and self.stop < self.start:
            raise InputError("stop must be greater than or equal to start.")
        if self.stride <= 0:
            raise InputError("stride must be a positive integer.")


@dataclass(frozen=True)
class SystemSummary:
    topology: str
    trajectory: str
    n_atoms: int
    n_frames: int | None
    species: dict[str, int]
    atom_names: dict[str, int]
    backend: str
    units: dict[str, str] = field(default_factory=lambda: {"coordinates": "nm", "time": "ps"})
    index_groups: dict[str, int] = field(default_factory=dict)
    role_suggestions: dict[str, SpeciesRoleSuggestion] = field(default_factory=dict)
    system_charge_e: float | None = None
    charge_tolerance_e: float = 1e-6
    schema_version: int = 1

    @property
    def has_net_charge(self) -> bool:
        return (
            self.system_charge_e is not None
            and abs(self.system_charge_e) > self.charge_tolerance_e
        )

    def to_dict(self) -> dict[str, Any]:
        for suggestion in self.role_suggestions.values():
            suggestion.validate()
        return asdict(self)
