"""Trajectory backend selection behind the core trajectory port."""

from __future__ import annotations

from pathlib import Path

from mdhelper.backends.gro import GroTrajectorySource
from mdhelper.backends.gromacs import GromacsTrajectorySource, TrajectoryConverter
from mdhelper.backends.mdanalysis import MDAnalysisTrajectorySource
from mdhelper.core.errors import BackendError
from mdhelper.core.trajectory import TrajectorySource


def load_trajectory(
    topology: str | Path,
    trajectory: str | Path,
    backend: str = "auto",
    cache_dir: str | Path | None = None,
    gromacs_converter: TrajectoryConverter | None = None,
) -> TrajectorySource:
    """Select a trajectory adapter from explicit policy or generic file capabilities."""

    topology_path = Path(topology)
    trajectory_path = Path(trajectory)
    if backend == "gromacs":
        if gromacs_converter is None:
            raise BackendError(
                "The GROMACS trajectory backend requires the GROMACS integration."
            )
        return GromacsTrajectorySource(
            topology, trajectory, gromacs_converter, cache_dir
        )
    if backend == "native" or (
        backend == "auto"
        and topology_path.suffix.casefold() == ".gro"
        and trajectory_path.suffix.casefold() == ".gro"
    ):
        return GroTrajectorySource(topology, trajectory)
    if backend in {"auto", "mdanalysis"}:
        return MDAnalysisTrajectorySource(topology, trajectory, cache_dir)
    raise BackendError(f"Unknown trajectory backend: {backend}")


__all__ = [
    "GroTrajectorySource",
    "GromacsTrajectorySource",
    "MDAnalysisTrajectorySource",
    "load_trajectory",
]
