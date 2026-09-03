"""GROMACS include-topology molecule definitions."""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from mdhelper.core.errors import FormatError, InputFileError


@dataclass(frozen=True)
class MoleculeType:
    name: str
    charge_e: float
    atom_count: int
    path: Path


@dataclass
class _MoleculeBuilder:
    name: str
    charge_e: Decimal = Decimal(0)
    atom_count: int = 0
    has_atoms_section: bool = False


def _section(line: str) -> str | None:
    if not line.startswith("[") or not line.endswith("]"):
        return None
    return line[1:-1].strip().casefold()


def _finish(
    records: list[MoleculeType],
    builder: _MoleculeBuilder | None,
    path: Path,
) -> None:
    if builder is None:
        return
    if not builder.has_atoms_section or builder.atom_count == 0:
        raise FormatError(
            f"Molecule type {builder.name!r} has no atom charges in {path}.",
            "Add a populated [ atoms ] section after its [ moleculetype ] section.",
            {"path": str(path), "molecule_type": builder.name},
        )
    charge_e = float(builder.charge_e)
    if not math.isfinite(charge_e):
        raise FormatError(
            f"Molecule type {builder.name!r} has an unrepresentable net charge in {path}.",
            details={"path": str(path), "molecule_type": builder.name},
        )
    records.append(
        MoleculeType(
            builder.name,
            charge_e,
            builder.atom_count,
            path,
        )
    )


def read_molecule_types(path: str | Path) -> tuple[MoleculeType, ...]:
    target = Path(path).expanduser().resolve()
    records: list[MoleculeType] = []
    builder: _MoleculeBuilder | None = None
    section = ""
    try:
        with target.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, 1):
                line = raw_line.split(";", 1)[0].strip()
                if not line:
                    continue
                if line.startswith("#"):
                    if section in {"moleculetype", "atoms"}:
                        raise FormatError(
                            f"A role-bearing section in {target} uses a preprocessor directive.",
                            "Provide an unambiguous [ moleculetype ] and [ atoms ] definition.",
                            {"path": str(target), "line": line_number},
                        )
                    continue
                next_section = _section(line)
                if next_section is not None:
                    if next_section == "moleculetype":
                        _finish(records, builder, target)
                        builder = None
                    elif next_section == "atoms" and builder is not None:
                        builder.has_atoms_section = True
                    section = next_section
                    continue
                fields = line.split()
                if section == "moleculetype":
                    if builder is not None:
                        raise FormatError(
                            f"The [ moleculetype ] section in {target} has multiple records.",
                            details={"path": str(target), "line": line_number},
                        )
                    builder = _MoleculeBuilder(fields[0])
                elif section == "atoms":
                    if builder is None:
                        raise FormatError(
                            f"An [ atoms ] section in {target} has no molecule type.",
                            "Place [ moleculetype ] before [ atoms ].",
                            {"path": str(target), "line": line_number},
                        )
                    if len(fields) < 7:
                        raise FormatError(
                            f"An atom record in {target} has no charge column.",
                            details={"path": str(target), "line": line_number},
                        )
                    try:
                        charge = Decimal(fields[6])
                    except InvalidOperation as exc:
                        raise FormatError(
                            f"An atom charge in {target} is not numeric.",
                            details={
                                "path": str(target),
                                "line": line_number,
                                "charge": fields[6],
                            },
                        ) from exc
                    if not charge.is_finite():
                        raise FormatError(
                            f"An atom charge in {target} is not finite.",
                            details={
                                "path": str(target),
                                "line": line_number,
                                "charge": fields[6],
                            },
                        )
                    builder.charge_e += charge
                    builder.atom_count += 1
    except (OSError, UnicodeError) as exc:
        raise FormatError(
            f"Could not read include topology: {target}",
            details={"path": str(target), "exception": f"{type(exc).__name__}: {exc}"},
        ) from exc
    _finish(records, builder, target)
    return tuple(records)


def find_itp_files(root: str | Path) -> tuple[Path, ...]:
    directory = Path(root).expanduser().resolve()
    if not directory.is_dir():
        raise InputFileError(
            "The species-role source is not a project directory.",
            details={"path": str(directory)},
        )
    try:
        return tuple(
            sorted(
                (
                    path
                    for path in directory.rglob("*")
                    if path.is_file() and path.suffix.casefold() == ".itp"
                ),
                key=lambda path: (
                    path.relative_to(directory).as_posix().casefold(),
                    path.relative_to(directory).as_posix(),
                ),
            )
        )
    except OSError as exc:
        raise InputFileError(
            "The project directory could not be scanned for include topologies.",
            details={"path": str(directory), "exception": f"{type(exc).__name__}: {exc}"},
        ) from exc


def discover_molecule_types(root: str | Path) -> dict[str, MoleculeType]:
    directory = Path(root).expanduser().resolve()
    definitions: dict[str, MoleculeType] = {}
    for path in find_itp_files(directory):
        for record in read_molecule_types(path):
            previous = definitions.get(record.name)
            if previous is not None:
                raise FormatError(
                    f"Molecule type {record.name!r} has multiple definitions in the project.",
                    "Keep one unambiguous molecule definition for automatic role detection.",
                    {
                        "molecule_type": record.name,
                        "paths": [str(previous.path), str(record.path)],
                    },
                )
            definitions[record.name] = record
    return dict(sorted(definitions.items()))
