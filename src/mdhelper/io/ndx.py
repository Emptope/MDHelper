"""Strict GROMACS index-group reader and selection adapter."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from mdhelper.core.errors import InputFileError, SelectionError
from mdhelper.core.system import Atom

NDX_SELECTION_LANGUAGE = "GROMACS index group file"
NDX_SELECTION_LANGUAGE_VERSION = "ndx-1"


def load_groups(index_file: str | Path, n_atoms: int) -> tuple[Path, dict[str, tuple[int, ...]]]:
    """Load ordered, zero-based groups from a one-based GROMACS index file."""

    path = Path(index_file).expanduser()
    if not path.is_file():
        raise InputFileError(
            f"GROMACS index file does not exist or is not readable: {path}",
            "Select a readable .ndx file or explicitly use MDAnalysis selection expressions.",
        )
    path = path.resolve()
    groups: dict[str, tuple[int, ...]] = {}
    current_name: str | None = None
    current_indices: list[int] = []

    def finish_group() -> None:
        nonlocal current_name, current_indices
        if current_name is None:
            return
        if current_name in groups:
            raise SelectionError(
                f"The GROMACS index group name {current_name!r} is duplicated.",
                "Rename duplicate groups so every requested name is unambiguous.",
                {"index_file": str(path), "group": current_name},
            )
        if len(set(current_indices)) != len(current_indices):
            raise SelectionError(
                f"GROMACS index group {current_name!r} contains duplicate atom numbers.",
                "Regenerate or edit the group so each atom appears once.",
                {"index_file": str(path), "group": current_name},
            )
        groups[current_name] = tuple(index - 1 for index in current_indices)
        current_name = None
        current_indices = []

    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError) as exc:
        raise InputFileError(
            f"Could not read GROMACS index file: {path}",
            "Save the index as UTF-8 text and check its permissions.",
            {"exception": f"{type(exc).__name__}: {exc}"},
        ) from exc
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.split(";", 1)[0].strip()
        if not line:
            continue
        header = re.fullmatch(r"\[\s*(.*?)\s*\]", line)
        if header:
            finish_group()
            current_name = header.group(1).strip()
            if not current_name:
                raise SelectionError(
                    "A GROMACS index group has an empty name.",
                    details={"index_file": str(path), "line": line_number},
                )
            continue
        if current_name is None:
            raise SelectionError(
                "A GROMACS index file contains atom numbers before its first group header.",
                "Start each group with a header such as '[ Cations ]'.",
                {"index_file": str(path), "line": line_number},
            )
        try:
            numbers = [int(value) for value in line.split()]
        except ValueError as exc:
            raise SelectionError(
                f"GROMACS index group {current_name!r} contains a non-integer atom number.",
                details={"index_file": str(path), "line": line_number, "value": raw_line},
            ) from exc
        invalid = [number for number in numbers if number < 1 or number > n_atoms]
        if invalid:
            raise SelectionError(
                f"GROMACS index group {current_name!r} refers to atoms outside the topology.",
                "GROMACS index atom numbers are one-based and must not exceed the topology size.",
                {
                    "index_file": str(path),
                    "line": line_number,
                    "topology_atoms": n_atoms,
                    "invalid_atom_numbers": invalid[:100],
                },
            )
        current_indices.extend(numbers)
    finish_group()
    if not groups:
        raise SelectionError(
            "The GROMACS index file contains no groups.",
            "Create groups with 'gmx make_ndx' or explicitly use selection expressions.",
            {"index_file": str(path)},
        )
    return path, groups


class NdxSelectionEngine:
    """Resolve exact group names from a GROMACS index file."""

    language = NDX_SELECTION_LANGUAGE
    language_version = NDX_SELECTION_LANGUAGE_VERSION

    def __init__(self, index_file: str | Path):
        self.index_file = index_file

    def resolve_many(
        self, atoms: Sequence[Atom], expressions: Sequence[str]
    ) -> tuple[tuple[int, ...], ...]:
        path, groups = load_groups(self.index_file, len(atoms))
        resolved: list[tuple[int, ...]] = []
        for group_name in expressions:
            name = group_name.strip()
            if not name:
                raise SelectionError("A GROMACS index group name cannot be empty.")
            if name not in groups:
                raise SelectionError(
                    f"GROMACS index group {name!r} was not found.",
                    "Choose one of the available groups or explicitly use a selection expression.",
                    {"index_file": str(path), "available_groups": list(groups)},
                )
            indices = groups[name]
            if not indices:
                raise SelectionError(
                    f"GROMACS index group {name!r} contains no atoms.",
                    "Populate the group or select a different group.",
                    {"index_file": str(path), "group": name},
                )
            resolved.append(indices)
        return tuple(resolved)
