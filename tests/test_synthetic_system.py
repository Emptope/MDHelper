from __future__ import annotations

import json
from pathlib import Path
from threading import Event
from typing import Literal, TypedDict

import numpy as np
import pytest

from mdhelper.analysis import AnalysisRegistry
from mdhelper.app import ApplicationService
from mdhelper.backends.gro import GroTrajectorySource
from mdhelper.cli import main
from mdhelper.core.analysis import AnalysisRequest, AnalysisResult, RadialRequest
from mdhelper.core.errors import InputFileError
from mdhelper.core.plotting import PlotLimits, PlotSelection, PlotState
from mdhelper.core.progress import ProgressCallback
from mdhelper.core.system import FrameRange
from mdhelper.core.trajectory import TrajectorySource
from mdhelper.plugins.analysis import FunctionBackend
from mdhelper.services.config import UserConfig


def _gro_atom(
    residue_id: int,
    residue_name: str,
    atom_name: str,
    atom_id: int,
    position: tuple[float, float, float],
) -> str:
    x, y, z = position
    return (
        f"{residue_id:5d}{residue_name:<5}{atom_name:>5}{atom_id:5d}"
        f"{x:8.3f}{y:8.3f}{z:8.3f}\n"
    )


def _write_trajectory(path: Path, n_frames: int = 2) -> None:
    base = (
        (
            0.0,
            (
                (1, "REF", "R", 1, (0.100, 0.100, 0.100)),
                (2, "LIGA", "A1", 2, (0.225, 0.100, 0.100)),
                (2, "LIGA", "A2", 3, (0.275, 0.100, 0.100)),
                (3, "LIGB", "B", 4, (1.900, 0.100, 0.100)),
            ),
        ),
        (
            1.0,
            (
                (1, "REF", "R", 1, (0.100, 0.100, 0.100)),
                (2, "LIGA", "A1", 2, (0.425, 0.100, 0.100)),
                (2, "LIGA", "A2", 3, (0.525, 0.100, 0.100)),
                (3, "LIGB", "B", 4, (1.400, 0.100, 0.100)),
            ),
        ),
    )
    frames = tuple(
        (float(index), base[index % len(base)][1]) for index in range(n_frames)
    )
    lines: list[str] = []
    for time_ps, atoms in frames:
        lines.extend((f"synthetic t={time_ps:g}\n", f"{len(atoms)}\n"))
        lines.extend(_gro_atom(*atom) for atom in atoms)
        lines.append("   2.00000   2.00000   2.00000\n")
    path.write_text("".join(lines), encoding="utf-8")


@pytest.fixture
def synthetic_path(tmp_path: Path) -> Path:
    path = tmp_path / "trajectory.gro"
    _write_trajectory(path)
    return path


class _Common(TypedDict):
    topology: str
    trajectory: str
    reference: str
    frames: FrameRange
    backend: Literal["native"]
    species_roles: dict[str, str]


def _common(path: Path) -> _Common:
    return {
        "topology": str(path),
        "trajectory": str(path),
        "reference": "resname REF",
        "frames": FrameRange(stop=2),
        "backend": "native",
        "species_roles": {"REF": "other", "LIGA": "other", "LIGB": "other"},
    }


def test_hand_checkable_rdf_and_coordination(synthetic_path: Path) -> None:
    application = ApplicationService(UserConfig())
    rdf = application.analyses.run(
        RadialRequest(
            analysis_type="rdf",
            selection="resname LIGA",
            r_max_nm=0.5,
            bin_width_nm=0.1,
            **_common(synthetic_path),
        )
    )
    histogram = np.asarray([0, 1, 1, 1, 1], dtype=float)
    edges = np.asarray([0.0, 0.05, 0.15, 0.25, 0.35, 0.45])
    shell_volume = (4.0 * np.pi / 3.0) * (edges[1:] ** 3 - edges[:-1] ** 3)
    assert rdf.data["radius_nm"] == pytest.approx([0.0, 0.1, 0.2, 0.3, 0.4])
    assert rdf.data["g_r"] == pytest.approx((histogram * 2.0 / shell_volume).tolist())
    assert "coordination_number" not in rdf.data

    coordination = application.analyses.run(
        RadialRequest(
            analysis_type="cumulative_rdf",
            selection="resname LIGA",
            r_max_nm=0.5,
            bin_width_nm=0.1,
            **_common(synthetic_path),
        )
    )
    cumulative_histogram = np.asarray([0, 2, 0, 1, 1], dtype=float)
    assert coordination.data["radius_nm"] == pytest.approx(
        [0.1, 0.2, 0.3, 0.4, 0.5]
    )
    assert coordination.data["cumulative_number"] == pytest.approx(
        np.cumsum(cumulative_histogram) / 2.0
    )
    assert "distribution_probability" not in coordination.data


def test_rdf_normalization_matches_gromacs_for_overlapping_selections(
    synthetic_path: Path,
) -> None:
    result = ApplicationService(UserConfig()).analyses.run(
        RadialRequest(
            analysis_type="rdf",
            reference="resname LIGA",
            selection="resname LIGA",
            topology=str(synthetic_path),
            trajectory=str(synthetic_path),
            r_max_nm=0.5,
            bin_width_nm=0.1,
            frames=FrameRange(stop=2),
            backend="native",
        )
    )
    edges = np.asarray([0.0, 0.05, 0.15, 0.25, 0.35, 0.45])
    shell_volume = (4.0 * np.pi / 3.0) * (edges[1:] ** 3 - edges[:-1] ** 3)

    assert np.sum(np.asarray(result.data["g_r"]) * shell_volume) == pytest.approx(4.0)
    assert result.diagnostics["possible_ordered_pairs_per_frame"] == 2
    assert result.diagnostics["normalization_ordered_pairs_per_frame"] == 4


def test_application_accepts_backend_neutral_trajectory_loader(synthetic_path: Path) -> None:
    source = GroTrajectorySource(synthetic_path, synthetic_path)
    calls: list[tuple[str, str, str]] = []

    def loader(topology: str, trajectory: str, backend: str) -> GroTrajectorySource:
        calls.append((topology, trajectory, backend))
        return source

    application = ApplicationService(UserConfig(), trajectory_loader=loader)
    result = application.analyses.run(
        RadialRequest(
            analysis_type="cumulative_rdf",
            selection="resname LIGA",
            r_max_nm=0.5,
            bin_width_nm=0.05,
            **_common(synthetic_path),
        )
    )

    assert calls == [(str(synthetic_path), str(synthetic_path), "native")]
    assert result.data["cumulative_number"][-1] == pytest.approx(2.0)


def test_system_inspection_always_uses_auto_trajectory_reader(
    synthetic_path: Path,
) -> None:
    source = GroTrajectorySource(synthetic_path, synthetic_path)
    calls: list[tuple[str, str, str]] = []

    def loader(topology: str, trajectory: str, backend: str) -> GroTrajectorySource:
        calls.append((topology, trajectory, backend))
        return source

    application = ApplicationService(UserConfig(), trajectory_loader=loader)

    application.checks.inspect_system(str(synthetic_path), str(synthetic_path))

    assert calls == [(str(synthetic_path), str(synthetic_path), "auto")]


def test_analysis_algorithm_is_replaceable_behind_application_contract(
    synthetic_path: Path,
) -> None:
    source = GroTrajectorySource(synthetic_path, synthetic_path)
    registry = AnalysisRegistry()

    def runner(
        source_value: TrajectorySource,
        request: AnalysisRequest,
        provenance: dict[str, object],
        progress: ProgressCallback | None,
        cancel_event: Event | None,
        max_pairs: int,
    ) -> AnalysisResult:
        assert source_value is source
        assert max_pairs > 0
        return AnalysisResult(
            analysis_type=request.analysis_type,
            data={"marker": 1},
            parameters={},
            units={"marker": "dimensionless"},
            diagnostics={},
            provenance=provenance,
            request=request.to_dict(),
        )

    registry.register("rdf", FunctionBackend(runner))
    application = ApplicationService(
        UserConfig(),
        trajectory_loader=lambda *_: source,
        analysis_registry=registry,
    )
    request = RadialRequest(
        analysis_type="rdf",
        selection="resname LIGA",
        r_max_nm=0.5,
        bin_width_nm=0.05,
        **_common(synthetic_path),
    )

    assert application.analyses.run(request).data == {"marker": 1}


def test_project_plot_state_round_trips_all_comparison_controls(
    synthetic_path: Path, tmp_path: Path
) -> None:
    application = ApplicationService(UserConfig())
    common = _common(synthetic_path)
    rdf_request = RadialRequest(
        analysis_type="rdf",
        selection="resname LIGA",
        r_max_nm=0.5,
        bin_width_nm=0.05,
        **common,
    )
    cn_request = RadialRequest(
        analysis_type="cumulative_rdf",
        selection="resname LIGB",
        r_max_nm=0.5,
        bin_width_nm=0.05,
        **common,
    )
    rdf = application.analyses.run(rdf_request)
    cn = application.analyses.run(cn_request)
    project = application.projects.create(
        tmp_path / "plot-state.mdhelper",
        synthetic_path,
        synthetic_path,
        species_roles=common["species_roles"],
    )
    application.projects.commit_result(project, rdf_request, rdf)
    application.projects.commit_result(project, cn_request, cn)
    state = PlotState(
        (
            PlotSelection(rdf.analysis_id, "RDF comparison", True, 0),
            PlotSelection(cn.analysis_id, "CN comparison", False, 1),
        ),
        "residue_name",
        PlotLimits(
            x_min=0.0,
            x_max=0.45,
            y_min=-0.2,
            y_max=4.0,
            y2_min=-1.0,
            y2_max=3.0,
        ),
    )
    application.projects.set_plot_state(project, state)

    reopened = application.projects.open(project.root)

    assert application.projects.plot_state(reopened) == state


def test_project_commit_binds_result_to_fingerprinted_inputs(
    synthetic_path: Path, tmp_path: Path
) -> None:
    changed = tmp_path / "changed.gro"
    changed.write_text(
        synthetic_path.read_text(encoding="utf-8").replace("   0.225", "   0.226"),
        encoding="utf-8",
    )
    application = ApplicationService(UserConfig())
    request = RadialRequest(
        analysis_type="cumulative_rdf",
        topology=str(changed),
        trajectory=str(changed),
        reference="resname REF",
        selection="resname LIGA",
        r_max_nm=0.5,
        bin_width_nm=0.05,
        frames=FrameRange(stop=2),
        backend="native",
    )
    result = application.analyses.run(request)
    project = application.projects.create(
        tmp_path / "bound.mdhelper", synthetic_path, synthetic_path
    )

    with pytest.raises(InputFileError, match="does not match"):
        application.projects.commit_result(project, request, result)

    assert not project.manifest["analyses"]
    assert not (
        project.root / "results" / "data" / f"{result.analysis_id}.json"
    ).exists()


def test_project_atomically_registers_explicit_index_on_first_commit(
    synthetic_path: Path, tmp_path: Path
) -> None:
    index = tmp_path / "groups.ndx"
    index.write_text("[ central ]\n1\n[ ligand ]\n2 3\n", encoding="utf-8")
    application = ApplicationService(UserConfig())
    request = RadialRequest(
        analysis_type="cumulative_rdf",
        topology=str(synthetic_path),
        trajectory=str(synthetic_path),
        index_file=str(index),
        reference="central",
        selection="ligand",
        r_max_nm=0.5,
        bin_width_nm=0.05,
        frames=FrameRange(stop=2),
        backend="native",
    )
    result = application.analyses.run(request)
    project = application.projects.create(
        tmp_path / "index.mdhelper", synthetic_path, synthetic_path
    )

    application.projects.commit_result(project, request, result)

    reopened = application.projects.open(project.root)
    assert reopened.resolve_inputs()["index"] == index.resolve()


def test_cli_completes_all_analyses_and_project_round_trip(
    synthetic_path: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = tmp_path / "cli.mdhelper"
    common = [
        "--project",
        str(project),
        "--backend",
        "native",
        "--role",
        "REF=other",
        "--role",
        "LIGA=other",
        "--role",
        "LIGB=other",
        "--stop",
        "2",
        "--no-figures",
    ]
    assert main(
        [
            "project",
            "create",
            "--path",
            str(project),
            "--topology",
            str(synthetic_path),
            "--trajectory",
            str(synthetic_path),
            "--role",
            "REF=other",
            "--role",
            "LIGA=other",
            "--role",
            "LIGB=other",
        ]
    ) == 0
    capsys.readouterr()

    commands = (
        [
            "rdf",
            *common,
            "--reference",
            "resname REF",
            "--selection",
            "resname LIGA",
            "--r-max",
            "0.5",
            "--bin-width",
            "0.05",
            "--output",
            str(tmp_path / "rdf"),
        ],
        [
            "cn",
            *common,
            "--reference",
            "resname REF",
            "--selection",
            "resname LIGA",
            "--r-max",
            "0.5",
            "--bin-width",
            "0.05",
            "--output",
            str(tmp_path / "cn"),
        ],
    )
    for command in commands:
        assert main(command) == 0
        capsys.readouterr()

    assert main(["project", "list-results", "--path", str(project)]) == 0
    result_types = {
        item["analysis_type"] for item in json.loads(capsys.readouterr().out)["analyses"]
    }
    assert result_types == {"rdf", "cumulative_rdf"}
