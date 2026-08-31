from __future__ import annotations

from pathlib import Path

import pytest

from mdhelper.core.analysis import AnalysisRequest, AnalysisResult


@pytest.fixture(autouse=True)
def _isolated_user_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MDHELPER_CONFIG", str(tmp_path / "config.toml"))


@pytest.fixture
def energy_result() -> AnalysisResult:
    request = AnalysisRequest(
        analysis_type="energy",
        topology="",
        trajectory="",
        reference="",
        energy_file="energy.edr",
        energy_terms=("Potential", "Temperature", "Pressure"),
        backend="gromacs",
    )
    return AnalysisResult(
        analysis_type="energy",
        data={
            "time_ps": [0.0, 1.0],
            "series": {
                "Potential": [-10.0, -9.0],
                "Temperature": [300.0, 301.0],
                "Pressure": [1.0, 1.5],
            },
        },
        parameters={},
        units={"time_ps": "ps", "series": "Value"},
        uncertainty={},
        diagnostics={},
        provenance={},
        request=request.to_dict(),
        analysis_id="energy-id",
    )
