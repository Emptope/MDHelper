"""Shared deterministic molecular input builders."""

from pathlib import Path


def gro_atom(
    residue_id: int,
    residue_name: str,
    atom_name: str,
    atom_id: int,
    position: tuple[float, float, float],
) -> str:
    x, y, z = position
    return (
        f"{residue_id:5d}{residue_name:<5}{atom_name:>5}{atom_id:5d}"
        f"{x:8.3f}{y:8.3f}{z:8.3f}\n"
    )


def write_trajectory(path: Path, n_frames: int = 2) -> None:
    base = (
        (
            (1, "REF", "C", 1, (0.100, 0.100, 0.100)),
            (2, "LIGA", "O1", 2, (0.225, 0.100, 0.100)),
            (2, "LIGA", "O2", 3, (0.275, 0.100, 0.100)),
            (3, "LIGB", "N", 4, (1.900, 0.100, 0.100)),
        ),
        (
            (1, "REF", "C", 1, (0.100, 0.100, 0.100)),
            (2, "LIGA", "O1", 2, (0.425, 0.100, 0.100)),
            (2, "LIGA", "O2", 3, (0.525, 0.100, 0.100)),
            (3, "LIGB", "N", 4, (1.400, 0.100, 0.100)),
        ),
    )
    lines: list[str] = []
    for index in range(n_frames):
        atoms = base[index % len(base)]
        lines.extend((f"synthetic t={float(index):g}\n", f"{len(atoms)}\n"))
        lines.extend(gro_atom(*atom) for atom in atoms)
        lines.append("   2.00000   2.00000   2.00000\n")
    path.write_text("".join(lines), encoding="utf-8")


def write_itp(path: Path, name: str, charges: tuple[str, ...]) -> None:
    atoms = "\n".join(
        f"{index} type 1 {name} A{index} {index} {charge} 1.0"
        for index, charge in enumerate(charges, 1)
    )
    path.write_text(
        "[ moleculetype ]\n"
        "; name nrexcl\n"
        f"{name} 3\n"
        "[ atoms ]\n"
        "; nr type resnr residue atom cgnr charge mass\n"
        f"{atoms}\n"
        "[ bonds ]\n"
        "1 1 1\n",
        encoding="ascii",
    )
