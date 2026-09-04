from __future__ import annotations

import warnings
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from mdhelper.analysis.radial.frames import selected_frame_count, validate_frame_selection
from mdhelper.backends.gromacs import GroTrajectorySource
from mdhelper.backends.mdanalysis import MDAnalysisTrajectorySource
from mdhelper.backends.trajectory import load_trajectory
from mdhelper.core.errors import FormatError, InputError, TopologyError, TrajectoryError
from mdhelper.core.system import Atom, FrameRange
from mdhelper.services.system import summarize_source


def test_frame_range_uses_python_stop_semantics(tmp_path: Path) -> None:
    from test_synthetic_system import _write_trajectory

    trajectory = tmp_path / "trajectory.gro"
    _write_trajectory(trajectory)
    source = GroTrajectorySource(trajectory, trajectory)

    assert [frame.index for frame in source.iter_frames(FrameRange(stop=1))] == [0]
    assert [frame.index for frame in source.iter_frames(FrameRange(start=1, stop=2))] == [1]
    assert [frame.index for frame in source.iter_frames(FrameRange())] == [0, 1]
    assert selected_frame_count(2, FrameRange(stop=1)) == 1
    assert selected_frame_count(2, FrameRange(stop=20, stride=2)) == 1
    assert validate_frame_selection(2, FrameRange(stop=1)) == 1
    with pytest.raises(InputError, match="exceeds the trajectory frame count") as stopped:
        validate_frame_selection(2, FrameRange(stop=20, stride=2))
    assert "Total frame count: 2" in stopped.value.message
    assert stopped.value.details == {"stop_frame": 20, "total_frames": 2}
    with pytest.raises(InputError, match="selects only one frame"):
        validate_frame_selection(101, FrameRange(stride=1_000_000_000))
    with pytest.raises(TrajectoryError, match="produced no frames"):
        list(source.iter_frames(FrameRange(start=1, stop=1)))


def test_gro_reader_accepts_extended_coordinate_precision(tmp_path: Path) -> None:
    path = tmp_path / "precise.gro"
    path.write_text(
        "precise t=2.5\n"
        "1\n"
        f"{1:5d}{'SOL':<5}{'OW':>5}{1:5d}"
        f"{0.123456:11.6f}{1.234567:11.6f}{2.345678:11.6f}\n"
        "3.000000000 3.000000000 3.000000000\n",
        encoding="ascii",
    )

    source = GroTrajectorySource(path, path)
    frame = next(source.iter_frames(FrameRange()))

    assert isinstance(frame.positions_nm, np.ndarray)
    assert frame.positions_nm == pytest.approx(
        np.asarray(((0.123456, 1.234567, 2.345678),))
    )


def test_auto_and_explicit_in_process_loading_use_mdanalysis(
    tmp_path: Path,
) -> None:
    from test_synthetic_system import _write_trajectory

    trajectory = tmp_path / "trajectory.gro"
    _write_trajectory(trajectory)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        automatic = load_trajectory(trajectory, trajectory, "auto")
        mdanalysis = load_trajectory(trajectory, trajectory, "mdanalysis")
        frame = next(mdanalysis.iter_frames(FrameRange(stop=1)))

    assert isinstance(automatic, MDAnalysisTrajectorySource)
    assert isinstance(mdanalysis, MDAnalysisTrajectorySource)
    assert mdanalysis.backend_name == "mdanalysis"
    assert frame.time_ps == 0.0


def test_species_role_suggestions_use_project_itp_evidence_not_names(tmp_path: Path) -> None:
    from test_itp import _write_itp

    _write_itp(tmp_path / "positive.itp", "alpha", ("1.0",))
    _write_itp(tmp_path / "negative.itp", "beta", ("-1.0",))
    _write_itp(tmp_path / "neutral.itp", "gamma", ("0.0",))
    atoms = (
        Atom(0, "X", "X", "alpha", 1, "alpha:1", -1.0),
        Atom(1, "Y", "Y", "beta", 2, "beta:2", 1.0),
        Atom(2, "Z", "Z", "gamma", 3, "gamma:3", 1.0),
        Atom(3, "Z", "Z", "gamma", 4, "gamma:4", 1.0),
        Atom(4, "Q", "Q", "delta", 5, "delta:5"),
    )
    source = SimpleNamespace(
        atoms=atoms,
        topology_path=Path("topology"),
        trajectory_path=Path("trajectory"),
        n_frames=1,
        backend_name="test",
    )

    summary = summarize_source(source, tmp_path)

    assert summary.role_suggestions["alpha"].suggested_role == "cation"
    assert summary.role_suggestions["beta"].suggested_role == "anion"
    assert summary.role_suggestions["gamma"].suggested_role == "solvent"
    assert summary.role_suggestions["delta"].suggested_role is None
    assert summary.role_suggestions["delta"].error
    serialized = summary.to_dict()
    assert serialized["schema_version"] == 1
    assert set(serialized["role_suggestions"]["alpha"]) == {
        "error",
        "evidence",
        "method",
        "suggested_role",
    }
    assert "role_definitions" not in serialized
    assert "role_policy" not in serialized
    assert summary.role_suggestions["alpha"].evidence == {
        "atom_count": 1,
        "molecule_charge_e": 1.0,
        "zero_tolerance_e": 1e-6,
        "source_file": "positive.itp",
    }
    assert "candidates" not in serialized["role_suggestions"]["alpha"]
def test_mdanalysis_xdr_offsets_are_stored_in_cache(tmp_path: Path) -> None:
    import MDAnalysis as mda

    topology = tmp_path / "topology.gro"
    trajectory = tmp_path / "trajectory.xtc"
    cache = tmp_path / "project" / "cache"
    universe = mda.Universe.empty(
        2,
        n_residues=1,
        atom_resindex=np.array([0, 0]),
        trajectory=True,
    )
    universe.add_TopologyAttr("names", ["A", "B"])
    universe.add_TopologyAttr("types", ["A", "B"])
    universe.add_TopologyAttr("resnames", ["SYS"])
    universe.add_TopologyAttr("resids", [1])
    universe.atoms.positions = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]])
    universe.dimensions = np.array([10.0, 10.0, 10.0, 90.0, 90.0, 90.0])
    with mda.Writer(str(topology), n_atoms=2) as writer:
        writer.write(universe.atoms)
    with mda.Writer(str(trajectory), n_atoms=2) as writer:
        universe.trajectory.ts.time = 2.5
        writer.write(universe.atoms)
        universe.atoms.positions += 0.5
        universe.trajectory.ts.time = 7.5
        writer.write(universe.atoms)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        source = MDAnalysisTrajectorySource(topology, trajectory, cache)
        frames = list(source.iter_frames(FrameRange()))

    assert source.n_frames == 2
    assert isinstance(frames[0].positions_nm, np.ndarray)
    assert frames[0].positions_nm == pytest.approx(
        np.asarray(((0.0, 0.0, 0.0), (0.1, 0.1, 0.1)))
    )
    assert [frame.time_ps for frame in frames] == [2.5, 7.5]
    assert len(tuple(cache.glob("*.offsets.npz"))) == 1
    assert not (tmp_path / ".trajectory.xtc_offsets.npz").exists()
    assert MDAnalysisTrajectorySource(topology, trajectory, cache).n_frames == 2


def test_gro_reader_rejects_identity_mismatch_and_empty_system(tmp_path: Path) -> None:
    from test_synthetic_system import _write_trajectory

    topology = tmp_path / "topology.gro"
    trajectory = tmp_path / "trajectory.gro"
    _write_trajectory(topology)
    trajectory.write_text(
        topology.read_text(encoding="utf-8").replace("   O1", "   Q1"),
        encoding="utf-8",
    )

    with pytest.raises(TopologyError, match="atom identities differ"):
        GroTrajectorySource(topology, trajectory)

    empty = tmp_path / "empty.gro"
    empty.write_text("empty\n0\n1 1 1\n", encoding="utf-8")
    with pytest.raises(FormatError, match="must be positive"):
        GroTrajectorySource(empty, empty)
