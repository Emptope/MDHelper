"""GROMACS-backed trajectory conversion behind the trajectory port."""

from __future__ import annotations

import hashlib
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from mdhelper.backends.gromacs.gro import GroTrajectorySource
from mdhelper.core.errors import BackendError
from mdhelper.core.system import Atom, Frame, FrameRange

TrajectoryConverter = Callable[[Path, Path, Path], dict[str, Any]]


def _cache_key(topology: Path, trajectory: Path) -> str:
    digest = hashlib.sha256()
    for path in (topology, trajectory):
        stat = path.stat()
        digest.update(str(path.resolve()).encode("utf-8"))
        digest.update(str(stat.st_size).encode("ascii"))
        digest.update(str(stat.st_mtime_ns).encode("ascii"))
    return digest.hexdigest()[:20]


class GromacsTrajectorySource:
    """Convert through local GROMACS, then stream the standard GRO representation."""

    backend_name = "gromacs"

    def __init__(
        self,
        topology: str | Path,
        trajectory: str | Path,
        converter: TrajectoryConverter,
        cache_dir: str | Path | None = None,
    ):
        self.topology_path = Path(topology).expanduser().resolve()
        self.trajectory_path = Path(trajectory).expanduser().resolve()
        self._temporary: tempfile.TemporaryDirectory[str] | None = None
        self._source: GroTrajectorySource | None = None
        if cache_dir is None:
            self._temporary = tempfile.TemporaryDirectory(prefix="mdhelper-gromacs-")
            root = Path(self._temporary.name)
        else:
            root = Path(cache_dir).expanduser().resolve()
            root.mkdir(parents=True, exist_ok=True)
        try:
            try:
                key = _cache_key(self.topology_path, self.trajectory_path)
            except OSError as exc:
                raise BackendError(
                    "Could not inspect inputs for the GROMACS trajectory backend.",
                    details={"exception": f"{type(exc).__name__}: {exc}"},
                ) from exc
            output = root / f"trajectory-{key}.gro"
            self.integration_run = converter(
                self.topology_path,
                self.trajectory_path,
                output,
            )
            if self.integration_run.get("status") != "completed" or not output.is_file():
                raise BackendError(
                    "GROMACS did not produce the converted trajectory.",
                    details={"integration_run": self.integration_run},
                )
            self._source = GroTrajectorySource(output, output)
            self.atoms: tuple[Atom, ...] = self._source.atoms
            self.n_frames: int = self._source.n_frames
        except BaseException:
            self.close()
            raise

    def iter_frames(self, frame_range: FrameRange) -> Iterator[Frame]:
        if self._source is None:
            raise BackendError("The GROMACS trajectory source is closed.")
        yield from self._source.iter_frames(frame_range)

    def close(self) -> None:
        if self._source is not None:
            self._source.close()
            self._source = None
        if self._temporary is not None:
            self._temporary.cleanup()
            self._temporary = None
