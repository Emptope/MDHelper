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
