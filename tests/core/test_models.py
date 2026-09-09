from __future__ import annotations

import copy
from string import ascii_letters, digits

import pytest
from hypothesis import given
from hypothesis import strategies as st

from mdhelper.core.analysis import (
    AnalysisRequest,
    AnalysisResult,
    EnergyRequest,
    RadialRequest,
)
from mdhelper.core.errors import ConfigurationError, InputError

_TOKEN = st.text(
    alphabet=ascii_letters + digits + "_-",
    min_size=1,
    max_size=20,
)


@st.composite
def _valid_request(draw) -> AnalysisRequest:
    backend = draw(st.sampled_from(("auto", "mdanalysis", "gromacs")))
    if draw(st.booleans()):
        r_max = draw(
            st.floats(
                min_value=0.001,
                max_value=100.0,
                allow_nan=False,
                allow_infinity=False,
            )
        )
        fraction = draw(
            st.floats(
                min_value=0.001,
                max_value=1.0,
                allow_nan=False,
                allow_infinity=False,
            )
        )
        return RadialRequest(
            analysis_type=draw(st.sampled_from(("rdf", "cumulative_rdf"))),
            analysis_backend=backend,
            topology=draw(_TOKEN),
            trajectory=draw(_TOKEN),
            reference=draw(_TOKEN),
            selection=draw(_TOKEN),
            r_max_nm=r_max,
            bin_width_nm=r_max * fraction,
        )
    terms = draw(st.lists(_TOKEN, min_size=1, max_size=8, unique=True))
    return EnergyRequest(
        analysis_type="energy",
        analysis_backend=backend,
        energy_file=draw(_TOKEN),
        energy_terms=tuple(terms),
    )


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
    with pytest.raises(InputError, match="Species-role suggestions"):
        RadialRequest(
            **{
                **_request().__dict__,
                "parameter_provenance": {"species_roles": {"A": {}}},
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


def test_request_parsing_rejects_malformed_field_shapes() -> None:
    with pytest.raises(ConfigurationError, match="JSON object"):
        AnalysisRequest.from_dict([])  # type: ignore[arg-type]
    with pytest.raises(ConfigurationError, match="supported schema"):
        AnalysisRequest.from_dict({"analysis_type": "removed"})  # type: ignore[dict-item]

    value = _request().to_dict()
    value.pop("topology")
    value["unknown"] = True
    with pytest.raises(ConfigurationError, match="missing or unknown fields"):
        AnalysisRequest.from_dict(value)

    value = _request().to_dict()
    value["frames"] = []
    with pytest.raises(ConfigurationError, match=r"frames.*object"):
        AnalysisRequest.from_dict(value)

    value = _request().to_dict()
    value["frames"] = {"start": 0}
    with pytest.raises(ConfigurationError, match=r"frames.*missing or unknown"):
        AnalysisRequest.from_dict(value)

    value = EnergyRequest(
        analysis_type="energy",
        energy_file="energy.edr",
        energy_terms=("Potential",),
    ).to_dict()
    value["energy_terms"] = [1]
    with pytest.raises(ConfigurationError, match=r"energy_terms.*array of strings"):
        AnalysisRequest.from_dict(value)


@pytest.mark.parametrize(
    ("candidate", "message"),
    (
        (
            RadialRequest(**{**_request().__dict__, "schema_version": 2}),
            "schema version",
        ),
        (
            RadialRequest(**{**_request().__dict__, "analysis_type": "energy"}),
            "radial analysis type",
        ),
        (
            RadialRequest(**{**_request().__dict__, "parameter_provenance": []}),
            "parameter_provenance",
        ),
        (RadialRequest(**{**_request().__dict__, "topology": ""}), "topology"),
        (RadialRequest(**{**_request().__dict__, "index_file": ""}), "index_file"),
        (RadialRequest(**{**_request().__dict__, "frames": {}}), "FrameRange"),
        (RadialRequest(**{**_request().__dict__, "r_max_nm": 0}), "r_max_nm"),
        (
            RadialRequest(**{**_request().__dict__, "bin_width_nm": 2.0}),
            "bin_width_nm",
        ),
        (
            RadialRequest(**{**_request().__dict__, "bin_width_nm": 1e-7}),
            "one million bins",
        ),
        (
            EnergyRequest(
                analysis_type="rdf",  # type: ignore[arg-type]
                energy_file="energy.edr",
                energy_terms=("Potential",),
            ),
            "energy analysis type",
        ),
        (
            EnergyRequest(
                analysis_type="energy",
                energy_file="",
                energy_terms=("Potential",),
            ),
            "energy_file",
        ),
        (
            EnergyRequest(
                analysis_type="energy",
                energy_file="energy.edr",
                energy_terms=[],  # type: ignore[arg-type]
            ),
            "energy_terms",
        ),
        (
            EnergyRequest(
                analysis_type="energy",
                energy_file="energy.edr",
                energy_terms=(),
            ),
            "at least one energy term",
        ),
        (
            EnergyRequest(
                analysis_type="energy",
                energy_file="energy.edr",
                energy_terms=("Potential", "Potential"),
            ),
            "duplicates",
        ),
    ),
)
def test_request_validation_rejects_invalid_contracts(
    candidate: AnalysisRequest,
    message: str,
) -> None:
    with pytest.raises(InputError, match=message):
        candidate.validate()


@given(_valid_request())
def test_valid_requests_round_trip(request: AnalysisRequest) -> None:
    assert AnalysisRequest.from_dict(request.to_dict()) == request


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
        data={"g_r": [1.0]},
        parameters={},
        units={"g_r": "dimensionless"},
        diagnostics={},
        provenance={},
        request=request.to_dict(),
    )
    value = result.to_dict()
    assert result.analysis_type == request.analysis_type
    assert "analysis_type" not in value
    assert "artifacts" not in value
    assert "uncertainty" not in value
    assert "status" not in value
    value["analysis_type"] = "rdf"
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
