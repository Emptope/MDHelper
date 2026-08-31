from __future__ import annotations

import pytest

from mdhelper.core.errors import ConfigurationError
from mdhelper.core.units import convert_distance


def test_distance_conversion_uses_a_single_canonical_scale() -> None:
    values = convert_distance((0.0, 0.25, 0.8), "nm", "angstrom")

    assert values == pytest.approx((0.0, 2.5, 8.0))
    assert convert_distance(values, "angstrom", "nm") == pytest.approx(
        (0.0, 0.25, 0.8)
    )


def test_distance_conversion_rejects_unknown_units() -> None:
    with pytest.raises(ConfigurationError, match="Unsupported distance conversion"):
        convert_distance((1.0,), "nm", "meter")  # type: ignore[arg-type]
