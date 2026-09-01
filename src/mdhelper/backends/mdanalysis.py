"""Optional MDAnalysis trajectory adapter."""

from __future__ import annotations

import math
import os
import re
import tempfile
import warnings
from collections.abc import Iterator
from hashlib import sha256
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from mdhelper.backends.common import infer_element, require_file
from mdhelper.core.errors import BackendError, TrajectoryError
from mdhelper.core.system import Atom, Box, Frame, FrameRange, Vec3

_CACHE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class _CachedOffsets:
    """Store XDR frame offsets outside the trajectory input directory."""

    _offset_path: Path
    _lock_path: Path
    _cache_enabled: bool
    filename: str
    _xdr: Any

    def __init__(self, filename: str, *args: Any, cache_dir: Path, **kwargs: Any):
        self._cache_enabled = True
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._cache_enabled = False
            warnings.warn(
                f"Could not prepare trajectory offset cache {cache_dir}: {exc}. "
                "Offsets will remain in memory for this run.",
                stacklevel=2,
            )
        source = Path(filename).expanduser().resolve()
        name = _CACHE_NAME.sub("_", source.name).strip("._") or "trajectory"
        key = sha256(str(source).encode("utf-8")).hexdigest()[:16]
        self._offset_path = cache_dir / f"{name}.{key}.offsets.npz"
        self._lock_path = cache_dir / f"{name}.{key}.offsets.lock"
        super().__init__(filename, *args, **kwargs)  # type: ignore[call-arg]

    def _load_offsets(self) -> None:
        import numpy as np
        from filelock import FileLock

        if not self._cache_enabled:
            self._read_offsets(store=False)
            return
        try:
            with FileLock(str(self._lock_path)):
                if self._offset_path.is_file():
                    try:
                        with np.load(self._offset_path, allow_pickle=False) as stored:
                            source = Path(self.filename).stat()
                            valid = (
                                int(stored["size"]) == source.st_size
                                and int(stored["mtime_ns"]) == source.st_mtime_ns
                                and int(stored["n_atoms"]) == self._xdr.n_atoms
                            )
                            offsets = stored["offsets"] if valid else None
                    except (KeyError, OSError, TypeError, ValueError):
                        offsets = None
                    if offsets is not None:
                        self._xdr.set_offsets(offsets)
                        return
                self._read_offsets(store=True)
        except OSError as exc:
            warnings.warn(
                f"Could not use trajectory offset cache {self._offset_path}: {exc}. "
                "Offsets will remain in memory for this run.",
                stacklevel=2,
            )
            self._read_offsets(store=False)

    def _read_offsets(self, store: bool = False) -> None:
        offsets = self._xdr.offsets
        if not store:
            return
        import numpy as np

        source = Path(self.filename).stat()
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f".{self._offset_path.name}.",
                suffix=".tmp",
                dir=self._offset_path.parent,
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                np.savez(
                    handle,
                    offsets=offsets,
                    size=source.st_size,
                    mtime_ns=source.st_mtime_ns,
                    n_atoms=self._xdr.n_atoms,
                )
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self._offset_path)
        except (OSError, TypeError, ValueError) as exc:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            warnings.warn(
                f"Could not save trajectory offsets in {self._offset_path}: {exc}",
                stacklevel=2,
            )


class MDAnalysisTrajectorySource:
    """Adapt an MDAnalysis Universe to MDHelper's trajectory port."""

    backend_name = "mdanalysis"
    backend_display_name = "MDAnalysis"

    def __init__(
        self,
        topology: str | Path,
        trajectory: str | Path,
        cache_dir: str | Path | None = None,
    ):
        self.topology_path = require_file(topology, "Topology")
        self.trajectory_path = require_file(trajectory, "Trajectory")
        try:
            import MDAnalysis as mda
            from MDAnalysis.coordinates.core import get_reader_for
            from MDAnalysis.coordinates.XDR import XDRBaseReader
            from MDAnalysis.exceptions import NoDataError
        except ImportError as exc:
            raise BackendError(
                "MDAnalysis is not installed, so this trajectory format cannot be read.",
                "Run 'uv sync'; use the MDHelper GRO Reader for GRO-only analysis.",
            ) from exc
        try:
            cache = (
                self.trajectory_path.parent / "cache"
                if cache_dir is None
                else Path(cache_dir).expanduser().resolve()
            )
            reader = get_reader_for(str(self.trajectory_path))
            if isinstance(reader, type) and issubclass(reader, XDRBaseReader):
                cached_reader = type(
                    f"Cached{reader.__name__}",
                    (_CachedOffsets, reader),
                    {},
                )
                self._universe = mda.Universe(
                    str(self.topology_path),
                    str(self.trajectory_path),
                    format=cached_reader,
                    cache_dir=cache,
                    to_guess=("types",),
                )
            else:
                self._universe = mda.Universe(
                    str(self.topology_path),
                    str(self.trajectory_path),
                    to_guess=("types",),
                )
        except Exception as exc:
            raise BackendError(
                "MDAnalysis could not load the topology/trajectory pair.",
                "Confirm that both files describe the same system and inspect the diagnostics.",
                {"backend_exception": f"{type(exc).__name__}: {exc}"},
            ) from exc
        atoms: list[Atom] = []
        for atom in self._universe.atoms:
            residue_name = str(getattr(atom, "resname", "UNK"))
            residue_id = int(getattr(atom, "resid", atom.index + 1))
            name = str(getattr(atom, "name", f"A{atom.index + 1}"))
            try:
                element = str(atom.element) or infer_element(name)
            except (AttributeError, KeyError, NoDataError, ValueError):
                element = infer_element(name)
            segid = str(getattr(atom, "segid", ""))
            molecule_id = f"{segid}:{residue_name}:{residue_id}"
            try:
                value = float(atom.charge)
                charge: float | None = value if math.isfinite(value) else None
            except (AttributeError, NoDataError, TypeError, ValueError):
                charge = None
            atoms.append(
                Atom(
                    int(atom.index),
                    name,
                    element,
                    residue_name,
                    residue_id,
                    molecule_id,
                    charge,
                )
            )
        self.atoms = tuple(atoms)
        self.n_frames = len(self._universe.trajectory)

    def iter_frames(self, frame_range: FrameRange) -> Iterator[Frame]:
        frame_range.validate()
        stop = (
            self.n_frames
            if frame_range.stop is None
            else min(frame_range.stop, self.n_frames)
        )
        yielded = 0
        for raw_index in range(frame_range.start, stop, frame_range.stride):
            try:
                timestep = self._universe.trajectory[raw_index]
                positions: NDArray[np.float64] = (
                    np.asarray(timestep.positions, dtype=np.float64) / 10.0
                )
                tri = timestep.triclinic_dimensions
                if tri is None:
                    vectors: tuple[Vec3, Vec3, Vec3] = (
                        (0.0, 0.0, 0.0),
                        (0.0, 0.0, 0.0),
                        (0.0, 0.0, 0.0),
                    )
                else:
                    vectors = (
                        (float(tri[0][0]) / 10.0, float(tri[0][1]) / 10.0, float(tri[0][2]) / 10.0),
                        (float(tri[1][0]) / 10.0, float(tri[1][1]) / 10.0, float(tri[1][2]) / 10.0),
                        (float(tri[2][0]) / 10.0, float(tri[2][1]) / 10.0, float(tri[2][2]) / 10.0),
                    )
                box = Box(vectors)
                box.validate()
                raw_time = timestep.data.get("time")
                time_ps = float(raw_index) if raw_time is None else float(raw_time)
                if not math.isfinite(time_ps):
                    raise TrajectoryError(
                        f"Frame {raw_index} has a non-finite time value."
                    )
            except Exception as exc:
                if isinstance(exc, TrajectoryError):
                    raise
                raise TrajectoryError(
                    f"Could not read frame {raw_index}.",
                    details={"backend_exception": f"{type(exc).__name__}: {exc}"},
                ) from exc
            yielded += 1
            yield Frame(raw_index, time_ps, positions, box)
        if yielded == 0:
            raise TrajectoryError("The requested frame range produced no frames.")

    def close(self) -> None:
        self._universe.trajectory.close()
