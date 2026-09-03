"""Backend-independent system inspection services."""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from threading import Event

from mdhelper.backends.trajectory import load_trajectory
from mdhelper.core.errors import BackendError
from mdhelper.core.progress import ProgressCallback
from mdhelper.core.system import Atom, SystemSummary
from mdhelper.core.trajectory import TrajectorySource
from mdhelper.integrations.gromacs import frame_progress, output_message
from mdhelper.integrations.manager import IntegrationManager

from .species import CHARGE_ZERO_TOLERANCE_E, inspect_species_roles

_TRAJECTORY_CACHE: ContextVar[str | Path | None] = ContextVar(
    "mdhelper_trajectory_cache", default=None
)


@contextmanager
def trajectory_cache(path: str | Path | None):
    """Set the cache used by the default trajectory loader in this context."""

    token = _TRAJECTORY_CACHE.set(path)
    try:
        yield
    finally:
        _TRAJECTORY_CACHE.reset(token)


def load_source(
    topology: str,
    trajectory: str,
    backend: str,
    integrations: IntegrationManager | None = None,
    cancel_event: Event | None = None,
    progress: ProgressCallback | None = None,
) -> TrajectorySource:
    """Load a trajectory behind the application-facing service boundary."""

    def convert(topology_path: Path, trajectory_path: Path, output: Path) -> dict[str, object]:
        if integrations is None:
            raise BackendError(
                "The GROMACS trajectory backend requires the GROMACS integration."
            )
        arguments = [
            "trjconv",
            "-s",
            str(topology_path),
            "-f",
            str(trajectory_path),
            "-o",
            str(output),
            "-ndec",
            "6",
        ]
        def process_progress(_elapsed: float, stdout: str, stderr: str) -> None:
            if progress is None:
                return
            message = output_message(stdout, stderr)
            if message is None:
                return
            frame = frame_progress(stdout, stderr)
            if frame is None:
                progress(0, None, message)
                return
            progress(frame[0] + 1, None, message)

        record = integrations.run(
            "gromacs",
            arguments,
            output.parent,
            cancel_event=cancel_event,
            output_files=[output],
            input_text="0\n",
            process_progress=process_progress,
            required_capabilities=("trjconv",),
        )
        if record.status != "completed":
            raise BackendError(
                f"GROMACS trajectory conversion exited with code {record.exit_code}.",
                details={"integration_run": record.to_dict()},
            )
        return record.to_dict()

    return load_trajectory(
        topology,
        trajectory,
        backend,
        _TRAJECTORY_CACHE.get(),
        convert if integrations is not None else None,
    )


def summarize_source(
    source: TrajectorySource,
    project_root: str | Path | None = None,
) -> SystemSummary:
    molecules_by_species: dict[str, dict[str, list[Atom]]] = {}
    atom_names: Counter[str] = Counter()
    for atom in source.atoms:
        molecules_by_species.setdefault(atom.residue_name, {}).setdefault(
            atom.molecule_id, []
        ).append(atom)
        atom_names[atom.name] += 1
    species = {
        key: len(value) for key, value in sorted(molecules_by_species.items())
    }
    inspection = inspect_species_roles(
        Path(source.trajectory_path).expanduser().resolve().parent
        if project_root is None
        else project_root,
        species,
    )
    return SystemSummary(
        topology=str(source.topology_path),
        trajectory=str(source.trajectory_path),
        n_atoms=len(source.atoms),
        n_frames=source.n_frames,
        species=species,
        atom_names=dict(sorted(atom_names.items())),
        backend=source.backend_name,
        role_suggestions=inspection.suggestions,
        system_charge_e=inspection.system_charge_e,
        charge_tolerance_e=CHARGE_ZERO_TOLERANCE_E,
    )
