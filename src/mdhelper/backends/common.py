"""Small helpers shared by trajectory backend adapters."""

from __future__ import annotations

from pathlib import Path

from mdhelper.core.errors import InputFileError

_TWO_LETTER_ELEMENTS = {"BR", "CA", "CL", "FE", "LI", "MG", "NA", "SI", "ZN"}


def infer_element(atom_name: str) -> str:
    """Infer an element label from an atom name without topology-specific rules."""

    letters = "".join(char for char in atom_name if char.isalpha()).upper()
    if not letters:
        return "X"
    if letters[:2] in _TWO_LETTER_ELEMENTS:
        return letters[:2].title()
    return letters[0]


def require_file(path: str | Path, role: str) -> Path:
    """Resolve a required input file and report an actionable domain error."""

    value = Path(path).expanduser()
    if not value.is_file():
        raise InputFileError(
            f"{role} file does not exist or is not readable: {value}",
            "Check the path, mount location, and file permissions.",
        )
    return value.resolve()
