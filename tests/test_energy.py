from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

from mdhelper.analysis.energy import MdaEnergy, parse_energy_terms
from mdhelper.app import ApplicationService
from mdhelper.core.analysis import AnalysisRequest
from mdhelper.core.errors import BackendError, FormatError
from mdhelper.core.plotting import result_plot
from mdhelper.core.system import FrameRange
from mdhelper.integrations.models import (
    IntegrationAdapter,
    IntegrationConfig,
    IntegrationRegistry,
)
from mdhelper.services.config import UserConfig


class _GromacsAdapter(IntegrationAdapter):
    name = "gromacs"
    display_name = "GROMACS"

    def __init__(self, program: Path):
        self.program = str(program)

    def candidate_names(self) -> tuple[str, ...]:
        return ()

    def command_prefix(self) -> tuple[str, ...]:
        return (self.program,)

    def parse_version(self, stdout: str, stderr: str, exit_code: int) -> str | None:
        return "test" if exit_code == 0 and "GROMACS version: test" in stdout else None

    def capability_arguments(self) -> tuple[str, ...]:
        return ("capabilities",)

    def parse_capabilities(self, stdout: str, stderr: str, exit_code: int) -> tuple[str, ...]:
        return ("energy", "trjconv", "rdf") if exit_code == 0 else ()


def _program(path: Path) -> Path:
    path.write_text(
        "from pathlib import Path\n"
        "import shutil\n"
        "import sys\n"
        "command = sys.argv[1]\n"
        "if command == '--version':\n"
        "    print('GROMACS version: test')\n"
        "elif command == 'capabilities':\n"
        "    print('energy trjconv rdf')\n"
        "elif command == 'energy':\n"
        "    selected = sys.stdin.read().strip()\n"
        "    output = Path(sys.argv[sys.argv.index('-o') + 1])\n"
        "    if selected == '0':\n"
        "        print('Select the terms you want from the following list by', "
        "file=sys.stderr)\n"
        "        print('End your selection with an empty line or a zero.', "
        "file=sys.stderr)\n"
        "        print('  1  Bond  2  Potential  3  Kinetic-En.', file=sys.stderr)\n"
        "        print('  4  Temperature  5  Pressure', file=sys.stderr)\n"
        "        raise SystemExit(1)\n"
        "    else:\n"
        '        output.write_text(\'@ yaxis label "Energy (kJ/mol)"\\n\' '
        "+ '0 1 10\\n1 2 20\\n', encoding='utf-8')\n"
        "elif command == 'trjconv':\n"
        "    source = Path(sys.argv[sys.argv.index('-f') + 1])\n"
        "    output = Path(sys.argv[sys.argv.index('-o') + 1])\n"
        "    if '-fr' in sys.argv:\n"
        "        frames = Path(sys.argv[sys.argv.index('-fr') + 1])\n"
        "        print(frames.read_text(encoding='ascii'), end='')\n"
        "    shutil.copyfile(source, output)\n"
        "elif command == 'rdf':\n"
        "    rdf = Path(sys.argv[sys.argv.index('-o') + 1])\n"
        "    cn = Path(sys.argv[sys.argv.index('-cn') + 1])\n"
        "    rdf.write_text('0.00 0.0\\n0.05 2.0\\n0.10 1.0\\n', encoding='utf-8')\n"
        "    cn.write_text('0.05 0.0\\n0.10 1.5\\n0.15 2.0\\n', encoding='utf-8')\n"
        "else:\n"
        "    raise SystemExit(2)\n",
        encoding="utf-8",
    )
    return path


def _application(tmp_path: Path) -> ApplicationService:
    registry = IntegrationRegistry()
    registry.register(_GromacsAdapter(_program(tmp_path / "gmx.py")))
    return ApplicationService(
        UserConfig(
            integrations={
                "gromacs": IntegrationConfig(path=str(Path(sys.executable)))
            }
        ),
        integration_registry=registry,
    )


def test_gromacs_energy_backend_standardizes_exports_and_project_data(
    tmp_path: Path,
) -> None:
    energy = tmp_path / "energy.edr"
    energy.write_bytes(b"energy")
    application = _application(tmp_path)
    request = AnalysisRequest(
        analysis_type="energy",
        topology="",
        trajectory="",
        reference="",
        energy_file=str(energy),
        energy_terms=("Potential", "Temperature"),
        backend="gromacs",
    )

    result = application.analyses.run(request)

    assert result.data == {
        "time_ps": [0.0, 1.0],
        "series": {"Potential": [1.0, 2.0], "Temperature": [10.0, 20.0]},
    }
    assert result.provenance["integration_runs"][0]["name"] == "gromacs"
    assert result.provenance["integration_runs"][0]["display_name"] == "GROMACS"
    assert result.provenance["analysis_backend"] == {
        "name": "gromacs",
        "display_name": "GROMACS",
    }
    model = result_plot(result)
    assert [series.label for series in model.series] == ["Potential", "Temperature"]
    output = tmp_path / "export"
    paths = application.analyses.export(result, output, include_figures=False)
    assert {path.name for path in paths} == {"result.json", "energy.csv"}
    with (output / "energy.csv").open(encoding="utf-8", newline="") as handle:
        assert list(csv.reader(handle)) == [
            ["time_ps", "Potential", "Temperature"],
            ["0", "1", "10"],
            ["1", "2", "20"],
        ]

    topology = tmp_path / "topology"
    trajectory = tmp_path / "trajectory"
    topology.write_bytes(b"topology")
    trajectory.write_bytes(b"trajectory")
    project = application.projects.create(
        tmp_path / "energy.mdhelper", topology, trajectory
    )
    result_path = application.projects.commit_result(project, request, result)
    entry = project.manifest["analyses"][0]
    stored_path = project.root / entry["result"]
    assert result_path.parent == project.root / "results" / "data"
    assert stored_path == result_path
    assert stored_path.is_file()
    reopened = application.projects.open(project.root)
    assert application.projects.load_result(reopened, result.analysis_id).data == result.data


def test_gromacs_energy_terms_are_discovered_from_the_selected_edr(
    tmp_path: Path,
) -> None:
    energy = tmp_path / "energy.edr"
    energy.write_bytes(b"energy")
    application = _application(tmp_path)

    assert application.analyses.energy_terms(energy, "gromacs") == (
        "Bond",
        "Potential",
        "Kinetic-En.",
        "Temperature",
        "Pressure",
    )


def test_auto_energy_backend_falls_back_to_available_gromacs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    energy = tmp_path / "energy.edr"
    energy.write_bytes(b"not an edr")
    application = _application(tmp_path)

    def unavailable(
        _backend: MdaEnergy, _inputs: object
    ) -> object:
        raise BackendError("MDAnalysis EDR support is unavailable.")

    monkeypatch.setattr(MdaEnergy, "run", unavailable)
    request = AnalysisRequest(
        analysis_type="energy",
        topology="",
        trajectory="",
        reference="",
        energy_file=str(energy),
        energy_terms=("Potential", "Temperature"),
        backend="auto",
    )

    result = application.analyses.run(request)

    assert result.provenance["analysis_backend"]["name"] == "gromacs"
    assert result.data["series"] == {
        "Potential": [1.0, 2.0],
        "Temperature": [10.0, 20.0],
    }


def test_mdanalysis_reads_terms_and_selected_series_from_edr() -> None:
    energy = Path("examples/LiFSI_DME_OPLS_0.8_small/md.edr").resolve()
    application = ApplicationService(UserConfig())

    terms = application.analyses.energy_terms(energy, "mdanalysis")

    assert terms[:4] == ("Bond", "Angle", "Ryckaert-Bell.", "Fourier Dih.")
    assert "Time" not in terms
    request = AnalysisRequest(
        analysis_type="energy",
        topology="",
        trajectory="",
        reference="",
        energy_file=str(energy),
        energy_terms=("Potential", "Total Energy"),
        backend="mdanalysis",
    )
    result = application.analyses.run(request)

    assert result.data["time_ps"][:3] == [0.0, 10.0, 20.0]
    assert tuple(result.data["series"]) == request.energy_terms
    assert len(result.data["series"]["Potential"]) == 101
    assert result.units == {"time_ps": "ps", "series": "kJ/mol"}
    assert result.diagnostics["series_units"] == {
        "Potential": "kJ/mol",
        "Total Energy": "kJ/mol",
    }
    assert result.provenance["analysis_backend"] == {
        "name": "mdanalysis",
        "display_name": "MDAnalysis",
    }
    assert "integration_runs" not in result.provenance


def test_mdanalysis_energy_rejects_a_term_absent_from_the_edr() -> None:
    energy = Path("examples/LiFSI_DME_OPLS_0.8_small/md.edr").resolve()
    request = AnalysisRequest(
        analysis_type="energy",
        topology="",
        trajectory="",
        reference="",
        energy_file=str(energy),
        energy_terms=("Not a term",),
        backend="mdanalysis",
    )

    with pytest.raises(FormatError, match="does not contain"):
        ApplicationService(UserConfig()).analyses.run(request)


def test_energy_term_parser_preserves_numbered_menu_order() -> None:
    output = """
Select the terms you want from the following list by
selecting either the name or number.
End your selection with an empty line or a zero.
  4  Temperature      5  Pressure
  1  Bond             2  Angle             3  Proper-Dih.
"""

    assert parse_energy_terms(output) == (
        "Bond",
        "Angle",
        "Proper-Dih.",
        "Temperature",
        "Pressure",
    )


@pytest.mark.parametrize(
    ("analysis_type", "expected_data"),
    (
        ("rdf", {"radius_nm": [0.0, 0.05, 0.1], "g_r": [0.0, 2.0, 1.0]}),
        (
            "cumulative_rdf",
            {
                "radius_nm": [0.05, 0.1, 0.15],
                "cumulative_number": [0.0, 1.5, 2.0],
            },
        ),
    ),
)
def test_gmx_rdf_uses_native_commands_and_frame_range(
    tmp_path: Path,
    analysis_type: str,
    expected_data: dict[str, list[float]],
) -> None:
    from test_synthetic_system import _write_trajectory

    synthetic_path = tmp_path / "trajectory.gro"
    _write_trajectory(synthetic_path, 6)
    index = tmp_path / "groups.ndx"
    index.write_text(
        "[ Reference group ]\n1\n[ Selection group ]\n2 3\n",
        encoding="ascii",
    )
    application = _application(tmp_path)
    progress: list[tuple[int, int | None, str]] = []
    request = AnalysisRequest(
        analysis_type=analysis_type,  # type: ignore[arg-type]
        topology=str(synthetic_path),
        trajectory=str(synthetic_path),
        index_file=str(index),
        reference="Reference group",
        selection="Selection group",
        r_max_nm=0.5,
        bin_width_nm=0.05,
        frames=FrameRange(0, 5, 2),
        backend="gromacs",
        species_roles={"REF": "other", "LIGA": "other", "LIGB": "other"},
    )

    result = application.analyses.run(
        request,
        lambda current, total, message: progress.append((current, total, message)),
        cache_dir=tmp_path / "cache",
    )

    assert result.diagnostics["n_frames"] == 3
    assert result.provenance["backend"] == "gromacs"
    assert result.provenance["analysis_backend"] == {
        "name": "gromacs",
        "display_name": "GROMACS",
    }
    assert result.provenance["trajectory_backend"] == {
        "name": "native-gro",
        "display_name": "Native GRO",
    }
    runs = result.provenance["integration_runs"]
    assert [run["arguments"][0] for run in runs] == ["trjconv", "rdf"]
    assert all(run["status"] == "completed" for run in runs)
    conversion_run, rdf_run = runs
    assert conversion_run["stdout"] == "[ frames ]\n1 3 5\n"
    rdf_source = rdf_run["arguments"][rdf_run["arguments"].index("-f") + 1]
    assert Path(rdf_source).name == "selected.xtc"
    rdf_topology = rdf_run["arguments"][rdf_run["arguments"].index("-s") + 1]
    assert Path(rdf_topology) == synthetic_path
    assert rdf_run["arguments"][rdf_run["arguments"].index("-ref") + 1] == (
        'group "Reference group"'
    )
    gromacs_progress = [item for item in progress if "GROMACS" in item[2]]
    assert gromacs_progress == [
        (3, 3, "Selected 3 GROMACS RDF frames"),
        (0, None, "Running GROMACS trajectory conversion"),
        (3, 3, "Prepared GROMACS RDF frames"),
        (0, None, "Running GROMACS RDF"),
        (3, 3, "Completed GROMACS RDF"),
    ]
    assert result.data == expected_data


def test_gmx_rdf_reads_original_inputs_without_trjconv(tmp_path: Path) -> None:
    from test_synthetic_system import _write_trajectory

    trajectory = tmp_path / "trajectory.gro"
    _write_trajectory(trajectory, 3)
    index = tmp_path / "groups.ndx"
    index.write_text(
        "[ Reference group ]\n1\n[ Selection group ]\n2 3\n",
        encoding="ascii",
    )
    result = _application(tmp_path).analyses.run(
        AnalysisRequest(
            analysis_type="rdf",
            topology=str(trajectory),
            trajectory=str(trajectory),
            index_file=str(index),
            reference="Reference group",
            selection="Selection group",
            r_max_nm=0.5,
            bin_width_nm=0.05,
            backend="gromacs",
            species_roles={"REF": "other", "LIGA": "other", "LIGB": "other"},
        )
    )

    runs = result.provenance["integration_runs"]
    assert [run["arguments"][0] for run in runs] == ["rdf"]
    arguments = runs[0]["arguments"]
    assert Path(arguments[arguments.index("-f") + 1]) == trajectory
    assert Path(arguments[arguments.index("-s") + 1]) == trajectory
    assert result.parameters["trajectory_preprocessing"]["source"] == (
        "original trajectory"
    )
