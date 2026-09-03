"""Numerical curve parsing for the GROMACS pipeline."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from mdhelper.core.errors import FormatError


def _parse_curve(path: Path, label: str) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    rows: list[tuple[float, float]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        raise FormatError(
            f"Could not read GROMACS {label} output: {path}",
            details={"exception": f"{type(exc).__name__}: {exc}"},
        ) from exc
    for line_number, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith(("#", "@")):
            continue
        fields = line.split()
        if len(fields) != 2:
            raise FormatError(
                f"GROMACS {label} output has an unexpected column count.",
                details={"line": line_number, "columns": len(fields)},
            )
        try:
            radius, value = (float(field) for field in fields)
        except ValueError as exc:
            raise FormatError(
                f"GROMACS {label} output contains a non-numeric row.",
                details={"line": line_number},
            ) from exc
        if not math.isfinite(radius) or not math.isfinite(value):
            raise FormatError(
                f"GROMACS {label} output contains a non-finite value.",
                details={"line": line_number},
            )
        rows.append((radius, value))
    if not rows:
        raise FormatError(f"GROMACS {label} output contains no numeric samples.")
    values = np.asarray(rows, dtype=np.float64)
    if len(values) > 1 and np.any(np.diff(values[:, 0]) <= 0):
        raise FormatError(f"GROMACS {label} radii are not strictly increasing.")
    return values[:, 0], values[:, 1]
