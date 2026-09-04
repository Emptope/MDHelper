from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

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


@given(
    st.lists(
        st.floats(
            min_value=-1e100,
            max_value=1e100,
            allow_nan=False,
            allow_infinity=False,
            width=64,
        ),
        max_size=50,
    )
)
def test_distance_conversion_round_trip(values: list[float]) -> None:
    converted = convert_distance(values, "nm", "angstrom")

    assert convert_distance(converted, "angstrom", "nm") == pytest.approx(values)
