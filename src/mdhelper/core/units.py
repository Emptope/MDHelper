"""Small, explicit unit conversions used at presentation boundaries."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from .errors import ConfigurationError

DistanceUnit = Literal["nm", "angstrom"]
ANGSTROM_SYMBOL = "\u00c5"

_NM_PER_UNIT: dict[DistanceUnit, float] = {
    "nm": 1.0,
    "angstrom": 0.1,
}


def convert_distance(
    values: Iterable[float],
    source: DistanceUnit,
    target: DistanceUnit,
) -> tuple[float, ...]:
    """Convert distance values through the canonical nanometer scale."""

    try:
        factor = _NM_PER_UNIT[source] / _NM_PER_UNIT[target]
    except KeyError as exc:
        raise ConfigurationError(
            f"Unsupported distance conversion: {source} to {target}."
        ) from exc
    return tuple(float(value) * factor for value in values)
