from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from mdhelper.analysis.radial import first_shell, first_shell_warnings


def _shell_curve(peak_height: float, dip_depth: float) -> tuple[np.ndarray, np.ndarray]:
    radii = np.linspace(0.0, 2.0, 41)
    rdf = (
        1.0
        + peak_height * np.exp(-((radii - 0.5) / 0.12) ** 2)
        - dip_depth * np.exp(-((radii - 0.9) / 0.15) ** 2)
    )
    return radii, rdf


@pytest.mark.parametrize(
    ("peak_height", "dip_depth"),
    (
        (1.2, 0.5),
        (0.3, 0.1),
        (0.15, 0.05),
    ),
)
def test_resolved_first_shell_reports_boundary(
    peak_height: float,
    dip_depth: float,
) -> None:
    shell = first_shell(*_shell_curve(peak_height, dip_depth))

    assert shell["available"] is True
    assert shell["first_minimum_nm"] == pytest.approx(0.9)
    assert "requires_user_confirmation" not in shell
    assert not first_shell_warnings(shell)


@pytest.mark.parametrize(
    ("radii", "rdf"),
    (
        (np.linspace(0.0, 1.0, 10), np.ones(10)),
        (np.linspace(0.0, 2.0, 41), np.ones(41)),
        (
            np.linspace(0.0, 2.0, 41),
            1.0
            + np.exp(-((np.linspace(0.0, 2.0, 41) - 0.5) / 0.12) ** 2),
        ),
    ),
)
def test_unresolved_first_shell_reports_warning(
    radii: np.ndarray,
    rdf: np.ndarray,
) -> None:
    shell = first_shell(radii, rdf)

    assert shell["available"] is False
    assert first_shell_warnings(shell)


@pytest.mark.parametrize("width", (0.025, 0.04, 0.06, 0.1))
def test_shell_extrema_are_resolved_on_raw_curve(width: float) -> None:
    radii = np.linspace(0.0, 2.0, 101)
    rdf = (
        1.0
        + 3.0 * np.exp(-((radii - 0.43) / width) ** 2)
        - 0.6 * np.exp(-((radii - 0.77) / 0.07) ** 2)
    )
    original = rdf.copy()

    shell = first_shell(radii, rdf)

    assert shell["available"] is True
    assert shell["first_peak_index"] == int(np.argmax(rdf))
    assert shell["first_minimum_index"] == int(np.argmin(rdf))
    assert shell["first_peak_g_r"] == float(np.max(rdf))
    assert shell["first_minimum_g_r"] == float(np.min(rdf))
    np.testing.assert_array_equal(rdf, original)


def test_narrow_peak_does_not_create_a_shell_minimum() -> None:
    radii = np.linspace(0.0, 2.0, 101)
    rdf = 1.0 + 3.0 * np.exp(-((radii - 0.43) / 0.025) ** 2)

    shell = first_shell(radii, rdf)

    assert shell["available"] is False
    assert shell["first_peak_index"] == int(np.argmax(rdf))
    assert shell["first_peak_g_r"] == float(np.max(rdf))
    assert "first_minimum_index" not in shell


@pytest.mark.parametrize(
    "values",
    ([0.0, 3.0, 0.5, 1.0, 1.0], [0.0, 3.0, 3.0, 0.5, 0.5, 1.0, 1.0]),
)
def test_short_curves_resolve_raw_extrema(values: list[float]) -> None:
    rdf = np.array(values)
    radii = np.arange(len(rdf), dtype=float) * 0.1

    shell = first_shell(radii, rdf)

    assert shell["available"] is True
    assert shell["first_peak_g_r"] == max(values)
    assert shell["first_minimum_g_r"] == min(values[1:])


@given(
    st.lists(
        st.floats(
            min_value=-100.0,
            max_value=100.0,
            allow_nan=False,
            allow_infinity=False,
        ),
        max_size=80,
    )
)
def test_first_shell_reports_consistent_boundaries(values: list[float]) -> None:
    rdf = np.asarray(values, dtype=np.float64)
    radii = np.arange(len(rdf), dtype=np.float64) * 0.01

    shell = first_shell(radii, rdf)

    if not shell["available"]:
        return
    peak = int(shell["first_peak_index"])
    minimum = int(shell["first_minimum_index"])
    assert 0 <= peak < minimum < len(rdf)
    assert shell["first_peak_nm"] == radii[peak]
    assert shell["first_minimum_nm"] == radii[minimum]
