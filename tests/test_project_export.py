from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError
from matplotlib import image as mpimg
from referencing import Registry, Resource

import mdhelper.project.inputs as input_module
import mdhelper.project.manifests as manifest_module
from mdhelper.app import ApplicationService
from mdhelper.core.analysis import AnalysisResult, EnergyRequest, RadialRequest
from mdhelper.core.errors import ConfigurationError, InputFileError
from mdhelper.core.plotting import PlotSize
from mdhelper.io.export import export_figures, export_result
from mdhelper.project import Project
from mdhelper.services.config import UserConfig

SCHEMA_ROOT = Path(__file__).parents[1] / "schemas"


def _validate_schema(value: dict[str, object], schema_name: str) -> None:
    registry = Registry()
    schemas: dict[str, dict[str, object]] = {}
    for path in SCHEMA_ROOT.glob("*.schema.json"):
        schema = json.loads(path.read_text(encoding="utf-8"))
        schemas[path.name] = schema
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    Draft202012Validator(
        schemas[schema_name],
        registry=registry,
        format_checker=FormatChecker(),
    ).validate(value)


def test_external_request_schema_uses_analysis_specific_fields() -> None:
    energy = EnergyRequest(
        analysis_type="energy",
        energy_file="energy.edr",
        energy_terms=("Potential",),
        analysis_backend="mdanalysis",
    )

    _validate_schema(energy.to_dict(), "analysis-request-v1.schema.json")


def test_external_request_schema_keeps_only_confirmed_species_roles() -> None:
    request = RadialRequest(
        analysis_type="rdf",
        topology="topology.gro",
        trajectory="trajectory.xtc",
        reference="reference",
        selection="selection",
        species_roles={"SOL": "solvent"},
    ).to_dict()

    _validate_schema(request, "analysis-request-v1.schema.json")

    request["parameter_provenance"] = {"species_roles": {"SOL": {}}}
    with pytest.raises(ValidationError):
        _validate_schema(request, "analysis-request-v1.schema.json")


def test_project_result_commit_is_atomic_and_verified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    topology = tmp_path / "topology"
    trajectory = tmp_path / "trajectory"
    topology.write_bytes(b"topology")
    trajectory.write_bytes(b"trajectory")
    project = Project.create(tmp_path / "project", topology, trajectory)
    request = RadialRequest(
        analysis_type="rdf",
        topology=str(topology),
        trajectory=str(trajectory),
        reference="reference",
        selection="selection",
    )
    input_files = {
        "topology": str(topology.resolve()),
        "trajectory": str(trajectory.resolve()),
    }
    result = AnalysisResult(
        data={"radius_nm": [0.1], "g_r": [1.0]},
        parameters={},
        units={"radius_nm": "nm", "g_r": "dimensionless"},
        diagnostics={},
        provenance={
            "input_files": input_files,
            "input_sha256": {
                value: project.manifest["inputs"][role]["sha256"]
                for role, value in input_files.items()
            },
        },
        request=request.to_dict(),
    )
    result_path = project.commit_result(request, result)
    entry = project.manifest["analyses"][0]
    stored_path = project.root / "results" / "data" / f"{result.analysis_id}.json"
    assert set(entry) == {
        "analysis_id",
        "result_sha256",
        "committed_at",
    }
    assert result_path.is_file()
    assert stored_path == result_path
    stored = json.loads(stored_path.read_text(encoding="utf-8"))
    assert "analysis_type" not in stored
    assert stored["data"] == result.data
    _validate_schema(request.to_dict(), "analysis-request-v1.schema.json")
    _validate_schema(stored, "analysis-result-v1.schema.json")
    _validate_schema(project.manifest, "project-v1.schema.json")
    listed = project.list_results()[0]
    assert listed["available"] is True
    assert listed["analysis_type"] == request.analysis_type
    assert listed["request"] == request.to_dict()
    assert listed["method_version"] == result.method_version

    failed = copy.deepcopy(result)
    failed.analysis_id = str(uuid4())
    original_atomic_json = manifest_module.atomic_json

    def fail_manifest(path: Path, value: dict[str, object]) -> None:
        if path == project.manifest_path:
            raise ConfigurationError("simulated interrupted manifest commit")
        original_atomic_json(path, value)

    monkeypatch.setattr(manifest_module, "atomic_json", fail_manifest)
    with pytest.raises(ConfigurationError, match="simulated interrupted"):
        project.commit_result(request, failed)
    assert not (project.root / "results" / "data" / f"{failed.analysis_id}.json").exists()
    monkeypatch.setattr(manifest_module, "atomic_json", original_atomic_json)

    reopened = Project.open(project.root)
    stored_path.write_text(stored_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="result fingerprint changed"):
        reopened.load_result(result.analysis_id)


def test_project_result_externalizes_integration_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    topology = tmp_path / "topology"
    trajectory = tmp_path / "trajectory"
    topology.write_text("topology", encoding="ascii")
    trajectory.write_text("trajectory", encoding="ascii")
    project = Project.create(tmp_path / "project", topology, trajectory)
    request = RadialRequest(
        analysis_type="rdf",
        topology=str(topology),
        trajectory=str(trajectory),
        reference="reference",
        selection="selection",
    )
    run = {
        "name": "tool",
        "display_name": "Tool",
        "path": "tool",
        "version": "1.0",
        "command": "tool run",
        "arguments": ["run"],
        "working_directory": str(tmp_path),
        "environment_summary": {},
        "exit_code": 0,
        "stdout": "standard output\n",
        "stderr": "standard error\n",
        "started_at": "2026-01-01T00:00:00+00:00",
        "output_fingerprints": {},
        "elapsed_seconds": 1.0,
        "status": "completed",
    }
    result = AnalysisResult(
        data={"radius_nm": [0.1], "g_r": [1.0]},
        parameters={},
        units={},
        diagnostics={},
        provenance={
            "input_files": {
                "topology": str(topology.resolve()),
                "trajectory": str(trajectory.resolve()),
            },
            "input_sha256": {
                str(topology.resolve()): project.manifest["inputs"]["topology"]["sha256"],
                str(trajectory.resolve()): project.manifest["inputs"]["trajectory"]["sha256"],
            },
            "integration_runs": [run],
        },
        request=request.to_dict(),
    )

    result_path = project.commit_result(request, result)

    stored_result = json.loads(result_path.read_text(encoding="utf-8"))
    stored_run = stored_result["provenance"]["integration_runs"][0]
    assert "integration_runs" not in project.manifest
    assert "integration_preferences" not in project.manifest
    assert "stdout" not in stored_run
    assert "stderr" not in stored_run
    assert "stdout_path" not in stored_run
    assert "stderr_path" not in stored_run
    for stream, extension in (("stdout", "out"), ("stderr", "err")):
        content = run[stream]
        path = project.root / "results" / "data" / f"{result.analysis_id}.{extension}"
        assert path.read_text(encoding="utf-8") == content
        assert stored_run[f"{stream}_sha256"] == hashlib.sha256(
            content.encode("utf-8")
        ).hexdigest()
    loaded_run = project.load_result(result.analysis_id).provenance["integration_runs"][0]
    assert loaded_run["stdout"] == run["stdout"]
    assert loaded_run["stderr"] == run["stderr"]
    _validate_schema(project.manifest, "project-v1.schema.json")

    existing_streams = set((project.root / "results" / "data").iterdir())
    failed = copy.deepcopy(result)
    failed.analysis_id = str(uuid4())
    original_atomic_json = manifest_module.atomic_json

    def fail_manifest(path: Path, value: dict[str, object]) -> None:
        if path == project.manifest_path:
            raise ConfigurationError("simulated log commit interruption")
        original_atomic_json(path, value)

    monkeypatch.setattr(manifest_module, "atomic_json", fail_manifest)
    with pytest.raises(ConfigurationError, match="simulated log commit interruption"):
        project.commit_result(request, failed)
    assert set((project.root / "results" / "data").iterdir()) == existing_streams
    assert not (project.root / "results" / "data" / f"{failed.analysis_id}.json").exists()


def test_direct_result_export_externalizes_run_streams(tmp_path: Path) -> None:
    request = RadialRequest(
        analysis_type="rdf",
        topology="topology",
        trajectory="trajectory",
        reference="A",
        selection="B",
    )
    run = {
        "name": "tool",
        "display_name": "Tool",
        "path": "tool",
        "version": "1.0",
        "command": "tool run",
        "arguments": ["run"],
        "working_directory": str(tmp_path),
        "environment_summary": {},
        "exit_code": 0,
        "stdout": "standard output\n",
        "stderr": "standard error\n",
        "started_at": "2026-01-01T00:00:00+00:00",
        "output_fingerprints": {},
        "elapsed_seconds": 1.0,
        "status": "completed",
    }
    result = AnalysisResult(
        data={"radius_nm": [0.1], "g_r": [1.0]},
        parameters={},
        units={},
        diagnostics={},
        provenance={"integration_runs": [run]},
        request=request.to_dict(),
    )

    paths = export_result(result, tmp_path)

    assert {path.name for path in paths} == {
        "result.json",
        "rdf.csv",
        "run.out",
        "run.err",
    }
    stored = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    stored_run = stored["provenance"]["integration_runs"][0]
    assert not {"stdout", "stderr", "stdout_path", "stderr_path"} & set(stored_run)
    assert (tmp_path / "run.out").read_text(encoding="utf-8") == run["stdout"]
    assert (tmp_path / "run.err").read_text(encoding="utf-8") == run["stderr"]


def test_export_removes_binary_float_noise(tmp_path: Path) -> None:
    request = RadialRequest(
        analysis_type="rdf",
        topology="topology",
        trajectory="trajectory",
        reference="A",
        selection="B",
        r_max_nm=0.01,
        bin_width_nm=0.002,
    )
    result = AnalysisResult(
        data={
            "radius_nm": [0.009000000000000001],
            "g_r": [1.2000000000000002],
        },
        parameters={"r_max_nm": 0.01, "bin_width_nm": 0.002},
        units={"radius_nm": "nm", "g_r": "dimensionless"},
        diagnostics={},
        provenance={},
        request=request.to_dict(),
    )

    export_result(result, tmp_path)

    metadata = (tmp_path / "result.json").read_text(encoding="utf-8")
    table = (tmp_path / "rdf.csv").read_text(encoding="utf-8")
    assert "0.009000000000000001" not in metadata
    assert "1.2000000000000002" not in metadata
    assert json.loads(metadata)["data"] == {"radius_nm": [0.009], "g_r": [1.2]}
    assert table.splitlines() == ["radius_nm,g_r", "0.009,1.2"]


def test_figure_export_preserves_requested_plot_size(tmp_path: Path) -> None:
    request = RadialRequest(
        analysis_type="rdf",
        topology="topology",
        trajectory="trajectory",
        reference="A",
        selection="B",
    )
    result = AnalysisResult(
        data={"radius_nm": [0.1, 0.2], "g_r": [0.0, 1.0]},
        parameters={},
        units={},
        diagnostics={},
        provenance={},
        request=request.to_dict(),
    )

    paths = export_figures(result, tmp_path, size=PlotSize(4.0, 3.0))

    assert {path.suffix for path in paths} == {".png", ".svg", ".pdf"}
    image = mpimg.imread(next(path for path in paths if path.suffix == ".png"))
    assert image.shape[:2] == (900, 1200)
    svg = next(path for path in paths if path.suffix == ".svg")
    assert "Radial distribution function" in svg.read_text(encoding="utf-8")
    pdf = next(path for path in paths if path.suffix == ".pdf")
    assert pdf.read_bytes().startswith(b"%PDF")


def test_project_feature_ensures_in_place_without_weakening_create(
    tmp_path: Path,
) -> None:
    topology = tmp_path / "topology.dat"
    trajectory = tmp_path / "trajectory.dat"
    topology.write_text("topology\n", encoding="ascii")
    trajectory.write_text("trajectory\n", encoding="ascii")

    with pytest.raises(ConfigurationError, match="not empty"):
        Project.create(tmp_path, topology, trajectory)

    application = ApplicationService(UserConfig())
    project, created = application.projects.ensure(tmp_path, topology, trajectory)

    assert created is True
    assert project.root == tmp_path.resolve()
    assert (tmp_path / "mdhelper-project.json").is_file()
    assert (tmp_path / "results").is_dir()
    assert (tmp_path / "figures").is_dir()

    reopened, created = application.projects.ensure(tmp_path, topology, trajectory)

    assert created is False
    assert reopened.root == project.root


def test_project_input_discovery_is_direct_case_insensitive_and_sorted(
    tmp_path: Path,
) -> None:
    for name in (
        "a.tpr",
        "B.GRO",
        "m.TRR",
        "n.tng",
        "groups.NDX",
        "molecule.ITP",
        "z.XTC",
        "notes.txt",
        "backup.gro.bak",
    ):
        (tmp_path / name).write_text("input\n", encoding="ascii")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "hidden.gro").write_text("input\n", encoding="ascii")
    (nested / "hidden.itp").write_text("input\n", encoding="ascii")

    application = ApplicationService(UserConfig())
    candidates = application.projects.discover_inputs(tmp_path)

    assert candidates.root == tmp_path.resolve()
    assert [path.name for path in candidates.topology] == ["a.tpr", "B.GRO"]
    assert [path.name for path in candidates.trajectory] == [
        "B.GRO",
        "m.TRR",
        "z.XTC",
    ]
    assert [path.name for path in candidates.index] == ["groups.NDX"]
    assert [path.relative_to(tmp_path).as_posix() for path in candidates.itp] == [
        "molecule.ITP",
        "nested/hidden.itp",
    ]


@pytest.mark.parametrize("trajectory_name", ["run.xtc", "run.trr"])
def test_project_input_discovery_accepts_supported_md_files(
    tmp_path: Path, trajectory_name: str
) -> None:
    topology = tmp_path / "system.tpr"
    trajectory = tmp_path / trajectory_name
    topology.write_text("topology\n", encoding="ascii")
    trajectory.write_text("trajectory\n", encoding="ascii")

    candidates = ApplicationService(UserConfig()).projects.discover_inputs(tmp_path)

    assert candidates.topology == (topology,)
    assert candidates.trajectory == (trajectory,)


def test_project_input_discovery_reports_missing_roles(tmp_path: Path) -> None:
    application = ApplicationService(UserConfig())
    topology_only = tmp_path / "topology-only"
    topology_only.mkdir()
    (topology_only / "system.tpr").write_text("input\n", encoding="ascii")
    trajectory_only = tmp_path / "trajectory-only"
    trajectory_only.mkdir()
    (trajectory_only / "run.xtc").write_text("input\n", encoding="ascii")

    with pytest.raises(InputFileError, match="trajectory"):
        application.projects.discover_inputs(topology_only)
    with pytest.raises(InputFileError, match="topology"):
        application.projects.discover_inputs(trajectory_only)
    with pytest.raises(InputFileError, match="not a directory"):
        application.projects.discover_inputs(tmp_path / "missing")


def test_project_open_accepts_manifest_path_and_ensure_rejects_other_inputs(
    tmp_path: Path,
) -> None:
    topology = tmp_path / "topology.dat"
    trajectory = tmp_path / "trajectory.dat"
    other = tmp_path / "other.dat"
    topology.write_text("topology\n", encoding="ascii")
    trajectory.write_text("trajectory\n", encoding="ascii")
    other.write_text("different\n", encoding="ascii")
    application = ApplicationService(UserConfig())
    project = application.projects.create(tmp_path / "project", topology, trajectory)

    assert application.projects.exists(project.root)
    assert not application.projects.exists(tmp_path / "not-a-project")
    reopened = application.projects.open(project.manifest_path)

    assert reopened.root == project.root
    with pytest.raises(ConfigurationError, match="different simulation inputs"):
        application.projects.ensure(project.root, topology, other)


def test_project_accepts_input_without_a_cross_volume_relative_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    topology = tmp_path / "topology"
    trajectory = tmp_path / "trajectory"
    topology.write_text("topology", encoding="utf-8")
    trajectory.write_text("trajectory", encoding="utf-8")
    original_relpath = input_module.os.path.relpath

    def unavailable(path: object, start: object) -> str:
        raise ValueError(f"No relative path from {start!r} to {path!r}")

    monkeypatch.setattr(input_module.os.path, "relpath", unavailable)
    project = Project.create(tmp_path / "cross-volume", topology, trajectory)
    monkeypatch.setattr(input_module.os.path, "relpath", original_relpath)

    assert Path(project.manifest["inputs"]["topology"]["path"]).is_absolute()
    _validate_schema(project.manifest, "project-v1.schema.json")
    assert Project.open(project.root).resolve_inputs()["topology"] == topology.resolve()


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda value: value.update({"unknown": True}), "unknown members"),
        (lambda value: value.pop("inputs"), "missing required members"),
        (lambda value: value.update({"inputs": []}), "must be an object"),
        (
            lambda value: value["inputs"]["topology"].update({"sha256": "invalid"}),
            "SHA-256",
        ),
        (lambda value: value.update({"created_at": "not-a-date"}), "date-time"),
    ],
)
def test_project_open_rejects_invalid_manifest_structure(
    tmp_path: Path, mutate: object, message: str
) -> None:
    topology = tmp_path / "topology"
    trajectory = tmp_path / "trajectory"
    topology.write_text("topology", encoding="utf-8")
    trajectory.write_text("trajectory", encoding="utf-8")
    project = Project.create(tmp_path / "project", topology, trajectory)
    value = json.loads(project.manifest_path.read_text(encoding="utf-8"))
    mutate(value)  # type: ignore[operator]
    project.manifest_path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ConfigurationError, match=message):
        Project.open(project.root, verify_inputs=False)


def test_project_open_rejects_redundant_analysis_metadata(tmp_path: Path) -> None:
    topology = tmp_path / "topology"
    trajectory = tmp_path / "trajectory"
    topology.write_text("topology", encoding="utf-8")
    trajectory.write_text("trajectory", encoding="utf-8")
    project = Project.create(tmp_path / "invalid-project", topology, trajectory)

    manifest = json.loads(project.manifest_path.read_text(encoding="utf-8"))
    manifest["analyses"].append(
        {
            "analysis_id": "invalid-analysis",
            "analysis_type": "rdf",
            "result_sha256": "0" * 64,
            "committed_at": manifest["created_at"],
        }
    )
    project.manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="unknown members"):
        Project.open(project.root, verify_inputs=False)
