"""Conservative cleanup of binary floating-point noise for presentation."""

from __future__ import annotations

import math


def clean_float(value: float) -> float:
    """Prefer 15 decimal digits only when rounding moves at most two float steps.

    This is an output policy, not a correction to analysis data. Preserve values
    that need more digits rather than rounding all results to fixed precision.
    """

    if not math.isfinite(value):
        return value
    if value == 0:
        return 0.0
    candidate = float(format(value, ".15g"))
    if abs(candidate - value) <= 2 * math.ulp(value):
        return candidate
    return value


def format_number(value: object) -> str:
    if isinstance(value, float):
        value = clean_float(value)
    return str(value)
