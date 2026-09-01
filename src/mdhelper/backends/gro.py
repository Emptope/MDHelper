"""Native streaming adapter for GRO topology and trajectory files."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import TextIO

import numpy as np

from mdhelper.backends.common import infer_element, require_file
from mdhelper.core.errors import FormatError, TopologyError, TrajectoryError
from mdhelper.core.system import Atom, Box, Frame, FrameRange


def _parse_atom(line: str, index: int) -> tuple[Atom, tuple[float, float, float]]:
    if len(line) < 44:
        raise FormatError("A GRO atom record is too short.", details={"line": line.rstrip()})
    try:
        residue_id = int(line[0:5])
        residue_name = line[5:10].strip()
        atom_name = line[10:15].strip()
        decimals = [position for position in range(20, len(line)) if line[position] == "."]
        width = decimals[1] - decimals[0] if len(decimals) >= 3 else 8
        coordinate_start = decimals[0] - 4 if len(decimals) >= 3 else 20
        x = float(line[coordinate_start : coordinate_start + width])
        y = float(line[coordinate_start + width : coordinate_start + 2 * width])
        z = float(line[coordinate_start + 2 * width : coordinate_start + 3 * width])
    except ValueError as exc:
        raise FormatError(
            "A GRO atom record contains an invalid number.", details={"line": line.rstrip()}
        ) from exc
    molecule_id = f"{residue_name}:{residue_id}"
    atom = Atom(
        index,
        atom_name,
        infer_element(atom_name),
        residue_name,
        residue_id,
        molecule_id,
    )
    return atom, (x, y, z)


def _parse_box(line: str) -> Box:
    try:
        values = [float(value) for value in line.split()]
    except ValueError as exc:
        raise FormatError("The GRO box record contains an invalid number.") from exc
    if len(values) == 3:
        vectors = ((values[0], 0.0, 0.0), (0.0, values[1], 0.0), (0.0, 0.0, values[2]))
    elif len(values) == 9:
        vectors = (
            (values[0], values[3], values[4]),
            (values[5], values[1], values[6]),
            (values[7], values[8], values[2]),
        )
    else:
        raise FormatError(
            f"A GRO box must contain 3 or 9 numbers; found {len(values)}.",
            "Check whether the file was truncated.",
        )
    return Box(vectors)


def _time(title: str, fallback: float) -> float:
    match = re.search(r"(?:^|\s)t\s*=\s*([-+0-9.eE]+)", title)
    if not match:
        return fallback
    try:
        return float(match.group(1))
    except ValueError:
        return fallback


def _read_frame(handle: TextIO, frame_index: int) -> tuple[tuple[Atom, ...], Frame] | None:
    title = handle.readline()
    while title and not title.strip():
        title = handle.readline()
    if not title:
        return None
    count_line = handle.readline()
    if not count_line:
        raise FormatError("The GRO file ended before the atom-count record.")
    try:
        n_atoms = int(count_line.strip())
    except ValueError as exc:
        raise FormatError(
            "The GRO atom count is not an integer.", details={"value": count_line.strip()}
        ) from exc
    if n_atoms <= 0:
        raise FormatError("The GRO atom count must be positive.", details={"value": n_atoms})
    atoms: list[Atom] = []
    positions: list[tuple[float, float, float]] = []
    for index in range(n_atoms):
        line = handle.readline()
        if not line:
            raise FormatError(f"The GRO file ended at atom {index + 1}/{n_atoms}.")
        atom, position = _parse_atom(line, index)
        atoms.append(atom)
        positions.append(position)
    box_line = handle.readline()
    if not box_line:
        raise FormatError("The GRO file has no periodic-box record.")
    frame = Frame(
        frame_index,
        _time(title, float(frame_index)),
        np.asarray(positions, dtype=np.float64),
        _parse_box(box_line),
    )
    return tuple(atoms), frame


class GroTrajectorySource:
    """Read single- or multi-frame GRO files through the trajectory port."""

    backend_name = "native"
    backend_display_name = "Native"

    def __init__(self, topology: str | Path, trajectory: str | Path):
        self.topology_path = require_file(topology, "Topology")
        self.trajectory_path = require_file(trajectory, "Trajectory")
        if self.topology_path.suffix.casefold() != ".gro":
            raise FormatError("The MDHelper GRO Reader supports GRO topology files only.")
        if self.trajectory_path.suffix.casefold() != ".gro":
            raise FormatError(
                "The MDHelper GRO Reader supports single- or multi-frame GRO trajectories only."
            )
        with self.topology_path.open("r", encoding="utf-8") as handle:
            parsed = _read_frame(handle, 0)
        if parsed is None:
            raise TopologyError("The topology GRO file is empty.")
        self.atoms = parsed[0]
        self.n_frames = self._count_frames()
        if self.n_frames == 0:
            raise TrajectoryError("The trajectory GRO file contains no frames.")

    def _validate_atoms(self, frame_atoms: tuple[Atom, ...], frame_index: int) -> None:
        if len(frame_atoms) != len(self.atoms):
            raise TrajectoryError(
                f"Atom count in frame {frame_index} differs from the topology.",
                details={
                    "topology_atoms": len(self.atoms),
                    "trajectory_atoms": len(frame_atoms),
                },
            )
        for topology_atom, trajectory_atom in zip(self.atoms, frame_atoms, strict=True):
            topology_identity = (
                topology_atom.residue_id,
                topology_atom.residue_name,
                topology_atom.name,
            )
            trajectory_identity = (
                trajectory_atom.residue_id,
                trajectory_atom.residue_name,
                trajectory_atom.name,
            )
            if topology_identity != trajectory_identity:
                raise TopologyError(
                    "Topology and trajectory atom identities differ at the same index.",
                    "Use topology and trajectory files from the same simulation with the same "
                    "atom ordering.",
                    {
                        "frame_index": frame_index,
                        "atom_index": topology_atom.index,
                        "topology_identity": topology_identity,
                        "trajectory_identity": trajectory_identity,
                    },
                )

    def _count_frames(self) -> int:
        count = 0
        with self.trajectory_path.open("r", encoding="utf-8") as handle:
            while True:
                parsed = _read_frame(handle, count)
                if parsed is None:
                    return count
                self._validate_atoms(parsed[0], count)
                count += 1

    def iter_frames(self, frame_range: FrameRange) -> Iterator[Frame]:
        frame_range.validate()
        with self.trajectory_path.open("r", encoding="utf-8") as handle:
            raw_index = 0
            yielded = 0
            while True:
                parsed = _read_frame(handle, raw_index)
                if parsed is None:
                    break
                frame_atoms, frame = parsed
                self._validate_atoms(frame_atoms, raw_index)
                if frame_range.stop is not None and raw_index >= frame_range.stop:
                    break
                if raw_index >= frame_range.start and (
                    (raw_index - frame_range.start) % frame_range.stride == 0
                ):
                    frame.box.validate()
                    yielded += 1
                    yield frame
                raw_index += 1
        if yielded == 0:
            raise TrajectoryError("The requested frame range produced no frames.")

    def close(self) -> None:
        pass
