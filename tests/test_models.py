from __future__ import annotations

import copy

import pytest

from mdhelper.core.analysis import (
    AnalysisRequest,
    AnalysisResult,
    EnergyRequest,
    RadialRequest,
)
from mdhelper.core.errors import ConfigurationError, InputError


def _request() -> AnalysisRequest:
    return RadialRequest(
        analysis_type="rdf",
        topology="topology.gro",
        trajectory="trajectory.gro",
        reference="resname A",
        selection="resname B",
        r_max_nm=0.5,
        bin_width_nm=0.005,
    )


def test_request_validation_rejects_non_schema_values() -> None:
    with pytest.raises(InputError, match="bin_width_nm"):
        RadialRequest(**{**_request().__dict__, "bin_width_nm": True}).validate()
    with pytest.raises(InputError, match="non-finite"):
        RadialRequest(
            **{
                **_request().__dict__,
                "parameter_provenance": {"decision": float("nan")},
            }
        ).validate()

    value = _request().to_dict()
    value["unknown"] = True
    with pytest.raises(ConfigurationError, match="unknown fields"):
        AnalysisRequest.from_dict(value)

    value = _request().to_dict()
    value.pop("bin_width_nm")
    with pytest.raises(ConfigurationError, match="missing fields"):
        AnalysisRequest.from_dict(value)


def test_requests_serialize_only_fields_used_by_the_analysis() -> None:
    radial = _request().to_dict()
    assert set(radial) == {
        "analysis_type",
        "topology",
        "trajectory",
        "reference",
        "selection",
        "r_max_nm",
        "bin_width_nm",
        "frames",
        "analysis_backend",
        "schema_version",
    }
    assert AnalysisRequest.from_dict(radial).to_dict() == radial

    energy = EnergyRequest(
        analysis_type="energy",
        energy_file="energy.edr",
        energy_terms=("Potential",),
        analysis_backend="mdanalysis",
    ).to_dict()
    assert energy == {
        "analysis_type": "energy",
        "energy_file": "energy.edr",
        "energy_terms": ["Potential"],
        "analysis_backend": "mdanalysis",
        "schema_version": 1,
    }
    assert AnalysisRequest.from_dict(energy).to_dict() == energy
    energy["topology"] = "unused.gro"
    with pytest.raises(ConfigurationError, match="unknown fields"):
        AnalysisRequest.from_dict(energy)


def test_radial_grid_counts_use_shared_half_width_histogram() -> None:
    request = RadialRequest(
        **{
            **_request().__dict__,
            "r_max_nm": 0.41,
            "bin_width_nm": 0.1,
        }
    )

    assert request.radial_fine_bin_count() == 8
    assert request.radial_bin_count() == 4
    assert request.cumulative_bin_count() == 4


def test_requests_reject_unknown_backend() -> None:
    with pytest.raises(InputError, match="Unknown analysis backend"):
        EnergyRequest(
            analysis_type="energy",
            energy_file="energy.edr",
            energy_terms=("Potential",),
            analysis_backend="removed",  # type: ignore[arg-type]
        ).validate()


def test_result_validation_rejects_unknown_and_non_json_content() -> None:
    request = _request()
    result = AnalysisResult(
        analysis_type="rdf",
        data={"g_r": [1.0]},
        parameters={},
        units={"g_r": "dimensionless"},
        diagnostics={},
        provenance={},
        request=request.to_dict(),
    )
    value = result.to_dict()
    assert "artifacts" not in value
    assert "uncertainty" not in value
    assert "status" not in value
    value["unknown"] = True
    with pytest.raises(ConfigurationError, match="unknown fields"):
        AnalysisResult.from_dict(value)

    value = result.to_dict()
    value.pop("method_version")
    with pytest.raises(ConfigurationError, match="missing fields"):
        AnalysisResult.from_dict(value)

    value = copy.deepcopy(result.to_dict())
    value["data"]["g_r"] = [float("inf")]
    with pytest.raises(ConfigurationError, match="non-finite"):
        AnalysisResult.from_dict(value)

    value = result.to_dict()
    value["artifacts"] = {}
    with pytest.raises(ConfigurationError, match="unknown fields"):
        AnalysisResult.from_dict(value)
