from __future__ import annotations

from mdhelper.app import result_exports
from mdhelper.core.analysis import AnalysisResult, EnergyRequest, RadialRequest
from mdhelper.core.species import SpeciesRoleSuggestion
from mdhelper.gui.formatting import role_suggestions_html


def _rdf_result() -> AnalysisResult:
    request = RadialRequest(
        analysis_type="rdf",
        topology="topology",
        trajectory="trajectory",
        reference="A",
        selection="B",
        r_max_nm=0.8,
        bin_width_nm=0.1,
    )
    return AnalysisResult(
        data={
            "radius_nm": [0.1, 0.2, 0.3],
            "g_r": [0.0, 3.0, 1.0],
        },
        parameters={"r_max_nm": 0.8, "bin_width_nm": 0.1},
        units={},
        diagnostics={
            "n_frames": 20,
            "first_shell_suggestion": {
                "available": True,
                "first_peak_nm": 0.2,
                "first_peak_g_r": 3.0,
                "first_minimum_nm": 0.3,
                "first_minimum_g_r": 1.0,
            },
        },
        provenance={},
        request=request.to_dict(),
        analysis_id="analysis-id",
        created_at="2026-08-29T04:00:00+00:00",
    )


def test_role_suggestion_evidence_is_rendered_as_readable_fields() -> None:
    source = "molecule<&>.itp"
    html = role_suggestions_html(
        {
            "sample": SpeciesRoleSuggestion(
                "solvent",
                "molecular net charge",
                {
                    "source_file": source,
                    "atom_count": 16,
                    "molecule_charge_e": -1e-10,
                    "matched_molecule_type": False,
                },
            )
        }
    )

    assert "<pre>" not in html
    assert "molecule_charge_e" not in html
    assert "molecule&lt;&amp;&gt;.itp" in html
    assert "-1e-10 e" in html


def test_unavailable_role_suggestion_keeps_its_error() -> None:
    error = "No matching molecule type in <project>."
    html = role_suggestions_html(
        {
            "sample": SpeciesRoleSuggestion(
                None,
                "molecular net charge",
                {"matched_molecule_type": False},
                error=error,
            )
        }
    )

    assert "No matching molecule type in &lt;project&gt;." in html


def test_result_export_name_describes_radial_pair() -> None:
    request = RadialRequest(
        analysis_type="rdf",
        topology=r"D:\runs\topology.tpr",
        trajectory=r"D:\runs\salt water.xtc",
        reference="resname LI",
        selection="name O*",
    )
    result = _rdf_result()
    result.request = request.to_dict()

    assert result_exports(result)[0].name == "rdf-resname-LI-name-O"

    result.request = RadialRequest(
        analysis_type="cumulative_rdf",
        topology="topology.tpr",
        trajectory="trajectory.xtc",
        reference="resname LI",
        selection="name O*",
    ).to_dict()

    assert result_exports(result)[0].name == "cn-resname-LI-name-O"


def test_result_exports_split_every_energy_curve_into_a_bounded_item() -> None:
    terms = tuple(f"Term {index:02d}" for index in range(46))
    request = EnergyRequest(
        analysis_type="energy",
        energy_file="/runs/equilibration.edr",
        energy_terms=terms,
    )
    result = AnalysisResult(
        data={
            "time_ps": [0.0],
            "series": {term: [float(index)] for index, term in enumerate(terms)},
        },
        parameters={},
        units={},
        diagnostics={},
        provenance={},
        request=request.to_dict(),
    )

    items = result_exports(result)

    assert len(items) == 46
    assert items[0].name == "energy-Term-00"
    assert items[-1].name == "energy-Term-45"
    assert all(len(item.name) <= 120 for item in items)
    for term, item in zip(terms, items, strict=True):
        item_request = EnergyRequest.from_dict(item.result.request)
        assert isinstance(item_request, EnergyRequest)
        assert item_request.energy_terms == (term,)
        assert tuple(item.result.data["series"]) == (term,)
