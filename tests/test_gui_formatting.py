from __future__ import annotations

from mdhelper.app.reports import (
    CoordinationReport,
    EnergyReport,
    RdfReport,
    Report,
    report_for,
)
from mdhelper.core.analysis import AnalysisRequest, AnalysisResult
from mdhelper.gui.formatting import result_label, result_summary, result_summary_html


def _rdf_result() -> AnalysisResult:
    request = AnalysisRequest(
        analysis_type="rdf",
        topology="topology",
        trajectory="trajectory",
        reference="A",
        selection="B",
        r_max_nm=0.8,
        bin_width_nm=0.1,
    )
    return AnalysisResult(
        analysis_type="rdf",
        data={
            "radius_nm": [0.1, 0.2, 0.3],
            "g_r": [0.0, 3.0, 1.0],
        },
        parameters={"r_max_nm": 0.8, "bin_width_nm": 0.1},
        units={},
        uncertainty={},
        diagnostics={
            "n_frames": 20,
            "first_shell_suggestion": {
                "available": True,
                "first_peak_nm": 0.2,
                "first_peak_g_r": 3.0,
                "first_minimum_nm": 0.3,
                "first_minimum_g_r": 1.0,
                "confidence": "high",
            },
        },
        provenance={},
        request=request.to_dict(),
        analysis_id="analysis-id",
        created_at="2026-08-29T04:00:00+00:00",
    )


def test_result_summary_prioritizes_results_and_reports_extrema() -> None:
    result = _rdf_result()
    assert isinstance(report_for(result), RdfReport)
    text = result_summary(result)

    assert text.index("Results") < text.index("Configuration")
    assert text.index("Configuration") < text.index("Technical details")
    assert text.index("Technical details") < text.index("Analysis ID")
    assert "g(r) maximum: 3 at 2 \u00c5" in text
    assert "g(r) minimum: 0 at 1 \u00c5" in text
    assert "First resolved peak: g(r) = 3 at 2 \u00c5" in text
    assert "First resolved minimum: g(r) = 1 at 3 \u00c5" in text
    assert "Calculated distance range: 0 to 8 \u00c5" in text
    assert "Bin width: 1 \u00c5" in text
    assert "Method: RDF 1.0.0" in text
    assert "Analysis backend: auto" in text


def test_result_summary_html_keeps_technical_metadata_last() -> None:
    text = result_summary_html(_rdf_result())

    assert text.index("Results") < text.index("Configuration")
    assert text.index("Configuration") < text.index("Technical details")
    assert text.index("Technical details") < text.index("analysis-id")


def test_result_summary_reports_every_integration_command_and_backend() -> None:
    request = AnalysisRequest(
        analysis_type="energy",
        topology="",
        trajectory="",
        reference="",
        energy_file="energy.edr",
        energy_terms=("Potential",),
        backend="gromacs",
    )
    result = AnalysisResult(
        analysis_type="energy",
        data={"time_ps": [0.0], "series": {"Potential": [-1.0]}},
        parameters={"analysis_backend": "gromacs"},
        units={"time_ps": "ps", "series": "Energy"},
        uncertainty={},
        diagnostics={"n_samples": 1},
        provenance={
            "analysis_backend": {
                "name": "gromacs",
                "display_name": "GROMACS",
            },
            "integration_runs": [
                {
                    "name": "gromacs",
                    "display_name": "GROMACS",
                    "version": "2020.6-MODIFIED",
                    "path": "D:/Software/gmx/bin/gmx.exe",
                    "arguments": ["energy", "-f", "energy.edr"],
                }
            ],
        },
        request=request.to_dict(),
    )

    text = result_summary(result)

    assert isinstance(report_for(result), EnergyReport)
    assert "Method: Energy 1.0.0" in text
    assert "Analysis backend: GROMACS" in text
    assert "External software: GROMACS" in text
    assert "Software version: 2020.6-MODIFIED" in text
    assert "Executable: D:/Software/gmx/bin/gmx.exe" in text
    assert "Command: energy" in text


def test_coordination_summary_reports_first_shell_instead_of_curve_extrema() -> None:
    request = AnalysisRequest(
        analysis_type="cumulative_rdf",
        topology="topology",
        trajectory="trajectory",
        reference="A",
        selection="B",
        r_max_nm=1.0,
        bin_width_nm=0.1,
    )
    result = AnalysisResult(
        analysis_type="cumulative_rdf",
        data={
            "radius_nm": [0.1, 0.2, 0.3, 0.4],
            "cumulative_number": [0.0, 1.0, 2.5, 4.0],
        },
        parameters={"r_max_nm": 1.0, "bin_width_nm": 0.1},
        units={},
        uncertainty={},
        diagnostics={
            "first_shell_suggestion": {
                "available": True,
                "first_minimum_nm": 0.3,
                "coordination_number": 2.5,
                "confidence": "high",
            }
        },
        provenance={},
        request=request.to_dict(),
    )

    text = result_summary(result)

    assert isinstance(report_for(result), CoordinationReport)
    assert text.startswith("CN completed")
    assert "First-shell coordination number: 2.5" in text
    assert "First-shell cutoff: 3 \u00c5 (first RDF minimum)" in text
    assert "Counting basis: Selection atoms per reference atom" in text
    assert "CN(r) maximum" not in text
    assert "CN(r) minimum" not in text
    assert "CN at maximum radius" not in text


def test_result_history_uses_compact_cn_label() -> None:
    text = result_label(
        {
            "analysis_type": "cumulative_rdf",
            "committed_at": "2026-08-30T11:58:11+00:00",
            "request": {"reference": "LI", "selection": "O_DME"},
        }
    )

    assert text.endswith(" | CN | LI-O_DME")


def test_energy_result_history_omits_absent_selection() -> None:
    text = result_label(
        {
            "analysis_type": "energy",
            "committed_at": "2026-08-30T11:58:11+00:00",
            "request": {"reference": "", "selection": None},
        }
    )

    assert text.endswith(" | Energy")
    assert "None" not in text


def test_every_analysis_report_inherits_the_shared_contract() -> None:
    assert all(
        issubclass(report_type, Report)
        for report_type in (
            RdfReport,
            CoordinationReport,
            EnergyReport,
        )
    )
