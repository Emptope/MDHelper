from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import pytest

from mdhelper.analysis.gromacs.backend import GromacsBackend
from mdhelper.analysis.gromacs.curves import _parse_curve
from mdhelper.analysis.pipeline import AnalysisInput
from mdhelper.app.reports.base import number
from mdhelper.core.analysis import AnalysisResult, AnalysisType, RadialRequest
from mdhelper.core.errors import ConfigurationError
from mdhelper.core.integrations import IntegrationRunRecord
from mdhelper.integrations.manager import IntegrationManager
from mdhelper.integrations.registry import IntegrationRegistry
from mdhelper.io.export.structured import export_result
from mdhelper.project import Project


@pytest.mark.parametrize("analysis_type", ("rdf", "cumulative_rdf"))
def test_radial_output_precision_survives_export(
    tmp_path: Path, analysis_type: AnalysisType
) -> None:
    source = tmp_path / "curve.xvg"
    source.write_text(
        "# Radial samples\n@ type xy\n"
        "0.12345678901234567 12.345678901234567\n"
        "0.23456789012345678 23.456789012345678\n",
        encoding="ascii",
    )
    radii, values = _parse_curve(source, analysis_type)
    column = "g_r" if analysis_type == "rdf" else "cumulative_number"
    request = RadialRequest(
        analysis_type=analysis_type,
        topology="topology",
        trajectory="trajectory",
        reference="A",
        selection="B",
    )
    result = AnalysisResult(
        data={"radius_nm": radii.tolist(), column: values.tolist()},
        parameters={},
        units={},
        diagnostics={},
        provenance={},
        request=request.to_dict(),
    )

    paths = export_result(result, tmp_path / "export")

    stored = json.loads(next(path for path in paths if path.suffix == ".json").read_text())
    assert stored["data"] == result.data
    with next(path for path in paths if path.suffix == ".csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [float(row["radius_nm"]) for row in rows] == radii.tolist()
    assert [float(row[column]) for row in rows] == values.tolist()
    assert all(float(number(float(value))) == value for value in values)


@pytest.mark.parametrize("analysis_type", ("rdf", "cumulative_rdf"))
def test_radial_pipeline_uses_raw_extrema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, analysis_type: AnalysisType
) -> None:
    source = tmp_path / "trajectory.gro"
    source.touch()
    radii = np.linspace(0.0, 2.0, 101)
    rdf = (
        1.0
        + 3.0 * np.exp(-((radii - 0.43) / 0.04) ** 2)
        - 0.6 * np.exp(-((radii - 0.77) / 0.07) ** 2)
    )
    cumulative_radii = radii[1:]
    cumulative = np.cumsum(rdf[1:]) * 0.12345678901234567
    manager = IntegrationManager({}, IntegrationRegistry())
    raw_outputs: dict[str, bytes] = {}
    working_directories: list[Path] = []

    def run(name: str, arguments: list[str], root: Path, **_kwargs: object):
        working_directories.append(root)
        for flag, x, y in (("-o", radii, rdf), ("-cn", cumulative_radii, cumulative)):
            if flag in arguments:
                path = Path(arguments[arguments.index(flag) + 1])
                content = "# Raw samples\r\n@ type xy\r\n" + "\r\n".join(
                    f"{r!r} {v!r}" for r, v in zip(x.tolist(), y.tolist(), strict=True)
                )
                raw_outputs[path.name] = content.encode("ascii")
                path.write_bytes(raw_outputs[path.name])
        return IntegrationRunRecord(
            name=name,
            display_name=name,
            path="tool",
            version="test",
            command=" ".join(arguments),
            arguments=arguments,
            working_directory=str(root),
            environment_summary={},
            exit_code=0,
            stdout="Reading frame 0 time 0.000\n",
            stderr="",
            started_at="2026-01-01T00:00:00+00:00",
        )

    monkeypatch.setattr(manager, "run", run)
    request = RadialRequest(
        analysis_type=analysis_type,
        topology=str(source),
        trajectory=str(source),
        reference="all",
        selection="all",
        r_max_nm=2.0,
        bin_width_nm=0.02,
        analysis_backend="gromacs",
    )

    provenance = {"input_files": {"topology": str(source), "trajectory": str(source)}}
    result = GromacsBackend().run(
        AnalysisInput(request, None, provenance, manager, None, None, None)
    )

    shell = result.diagnostics["first_shell_suggestion"]
    assert shell["available"]
    assert shell["first_peak_nm"] == radii[np.argmax(rdf)]
    assert shell["first_minimum_nm"] == radii[np.argmin(rdf)]
    if analysis_type == "cumulative_rdf":
        index = np.searchsorted(cumulative_radii, radii[np.argmin(rdf)])
        assert shell["coordination_number"] == cumulative[index]
        assert result.data["cumulative_number"] == cumulative.tolist()
    else:
        assert result.data["g_r"] == rdf.tolist()

    assert all(not root.exists() for root in working_directories)
    record = result.provenance["integration_runs"][0]
    assert record["output_texts"] == {
        name: content.decode("ascii") for name, content in raw_outputs.items()
    }
    project = Project.create(tmp_path / "project", source, source)
    project.commit_result(request, result)
    restored = Project.open(project.root).load_result(result.analysis_id)
    assert restored.provenance["integration_runs"] == result.provenance["integration_runs"]
    paths = export_result(restored, tmp_path / "export")
    expected_names = {"rdf.xvg"}
    if analysis_type == "cumulative_rdf":
        expected_names.add("cn.xvg")
    assert {path.name for path in paths if path.suffix == ".xvg"} == expected_names
    for name, content in raw_outputs.items():
        exported = next(path for path in paths if path.name == name)
        assert exported.read_bytes() == content
    assert (tmp_path / "export" / "run.out").read_text() == record["stdout"]
    assert (tmp_path / "export" / "run.err").read_text() == record["stderr"]
    stored = json.loads((tmp_path / "export" / "result.json").read_text())
    assert "output_texts" not in stored["provenance"]["integration_runs"][0]
    archived_output = next((project.root / "results" / "data").glob("*.xvg"))
    archived_output.write_bytes(b"changed")
    with pytest.raises(ConfigurationError, match="fingerprint"):
        Project.open(project.root).load_result(result.analysis_id)
