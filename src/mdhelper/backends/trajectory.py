"""Trajectory backend selection behind the core trajectory port."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from mdhelper.core.errors import BackendError
from mdhelper.core.trajectory import TrajectorySource

if TYPE_CHECKING:
    from mdhelper.backends.gromacs import TrajectoryConverter


def load_trajectory(
    topology: str | Path,
    trajectory: str | Path,
    backend: str = "auto",
    cache_dir: str | Path | None = None,
    gromacs_converter: TrajectoryConverter | None = None,
) -> TrajectorySource:
    """Select a trajectory adapter from explicit policy or generic file capabilities."""

    if backend == "gromacs":
        from mdhelper.backends.gromacs import GromacsTrajectorySource

        if gromacs_converter is None:
            raise BackendError(
                "The GROMACS trajectory backend requires the GROMACS integration."
            )
        return GromacsTrajectorySource(
            topology, trajectory, gromacs_converter, cache_dir
        )
    if backend in {"auto", "mdanalysis"}:
        from mdhelper.backends.mdanalysis import MDAnalysisTrajectorySource

        return MDAnalysisTrajectorySource(topology, trajectory, cache_dir)
    raise BackendError(f"Unknown trajectory backend: {backend}")


__all__ = ["load_trajectory"]
