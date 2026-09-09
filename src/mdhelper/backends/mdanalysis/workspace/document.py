"""Read-only, paged access to parsed molecular file data."""

from __future__ import annotations

import inspect
import json
from collections.abc import Generator, Iterator, Mapping
from pathlib import Path
from threading import Event
from typing import Any

from mdhelper.core.errors import BackendError, JobCancelled
from mdhelper.core.workspace import DataLayout, DataPage, DataSection


class BinaryDocument:
    def __init__(self, path: Path):
        self._reader: Any = None
        self._universe: Any = None
        self._auxiliary = False
        self._static: dict[str, Any] = {}
        self._values: dict[str, Any] = {}
        self.frames: int | None = 0
        self.layout = DataLayout()
        self._fields: tuple[str, ...] = ()
        try:
            self._open(path)
            self.select_frame(0)
            self._configure_series()
        except BaseException:
            self.close()
            raise

    def _open(self, path: Path) -> None:
        import MDAnalysis as mda
        from MDAnalysis.auxiliary.core import get_auxreader_for
        from MDAnalysis.coordinates.XDR import XDRBaseReader

        from mdhelper.backends.mdanalysis.formats import get_parser, get_reader

        from .streams import EnergyStream, SequentialXdr

        options: dict[str, Any] = {}
        try:
            coordinate_reader = get_reader(str(path))
            if issubclass(coordinate_reader, XDRBaseReader):
                coordinate_reader = type("WorkspaceReader", (SequentialXdr, coordinate_reader), {})
            self._reader = coordinate_reader(str(path), **options)
        except (ValueError, TypeError, OSError):
            self._reader = None
        try:
            parser = get_parser(str(path))
            options = {} if self._reader is None else {"n_atoms": self._reader.n_atoms}
            with parser(str(path)) as topology_parser:
                topology = topology_parser.parse(**options)
            self._universe = mda.Universe(topology, to_guess=())
        except (ValueError, TypeError, OSError):
            self._universe = None
        if self._universe is not None:
            topology = self._universe._topology
            for attr in topology.attrs:
                if hasattr(attr, "values"):
                    self._add(self._static, f"topology/{attr.attrname}", attr.values)
                for name in ("types", "order"):
                    value = getattr(attr, name, None)
                    if value is not None:
                        self._add(self._static, f"topology/{attr.attrname}/{name}", value)
            self._static["topology/atom_resindex"] = self._universe.atoms.resindices
            self._static["topology/residue_segindex"] = self._universe.residues.segindices
        if self._reader is None and self._universe is None:
            reader = get_auxreader_for(str(path))
            reader = {"EDR": EnergyStream}.get(getattr(reader, "format", ""), reader)
            options = {}
            if "convert_units" in inspect.signature(reader).parameters:
                options["convert_units"] = False
            self._reader = reader(str(path), **options)
            self._auxiliary = True
        if self._reader is not None:
            if getattr(self._reader, "sequential", False):
                self.frames = None
            else:
                self.frames = self._reader.n_steps if self._auxiliary else len(self._reader)
            self._add(self._static, "units", getattr(self._reader, "units", {}))
            self._add(self._static, "units", getattr(self._reader, "unit_dict", {}))
        if not self._static and self._reader is None:
            raise BackendError(f"No readable data in {path}")

    def _configure_series(self) -> None:
        if not self._auxiliary or not isinstance(self._reader.auxstep.data, Mapping):
            return
        fields = list(getattr(self._reader, "fields", self._reader.auxstep.data))
        time = self._reader.time_selector
        if time in fields:
            fields.remove(time)
            fields.insert(0, time)
        self._fields = tuple(fields)
        units = getattr(self._reader, "unit_dict", {})
        columns = ("Frame", *(f"{name} ({units[name]})" if units.get(name) else str(name)
                              for name in fields))
        self.layout = DataLayout(columns, tuple(
            index for index, name in enumerate(fields, 1) if name != time
        ))

    def _series_records(self, cancel: Event | None) -> Iterator[tuple[tuple[str, ...], ...]]:
        for frame, step in enumerate(self._steps()):
            if cancel is not None and cancel.is_set():
                raise JobCancelled("File loading cancelled")
            data = step.data
            yield ((str(frame), *(self._text(data[name]) if name in data else ""
                                  for name in self._fields)),)

    @staticmethod
    def _add(target: dict[str, Any], name: str, value: Any) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                BinaryDocument._add(target, f"{name}/{key}", item)
        elif value is not None:
            target[name] = value

    def _steps(self) -> Iterator[Any]:
        if self._reader is None:
            return
        if self.frames is None:
            yield from self._reader.steps()
        else:
            for index in range(self.frames):
                yield self._reader[index]

    def select_frame(self, index: int) -> tuple[DataSection, ...]:
        if self.frames is None:
            step = self._reader.auxstep if self._auxiliary else self._reader.ts
            if index != 0:
                raise IndexError("Sequential reader only exposes its current frame")
        elif self._reader is not None:
            if not 0 <= index < self.frames:
                raise IndexError(index)
            step = self._reader[index]
        else:
            step = None
        return self._set_step(step)

    def _set_step(self, step: Any) -> tuple[DataSection, ...]:
        self._values = dict(self._static)
        if step is not None:
            self._add(self._values, "data", step.data)
            if self._auxiliary:
                self._add(self._values, "time", step.time)
            else:
                # Do not expose inferred defaults as recorded physical metadata.
                if "time" in step.data or "dt" in step.data:
                    self._add(self._values, "time", step.time)
                if "dt" in step.data:
                    self._add(self._values, "dt", step.data["dt"])
                if step.dimensions is not None:
                    self._add(self._values, "dimensions", step.dimensions)
                    self._add(self._values, "volume", step.volume)
                for name in ("positions", "velocities", "forces"):
                    if getattr(step, f"has_{name}"):
                        self._add(self._values, name, getattr(step, name))
        return tuple(self._section(name) for name in self._values)

    def _section(self, name: str) -> DataSection:
        value = self._values[name]
        shape: Any = getattr(value, "shape", ())
        if len(shape) > 1:
            columns = tuple(str(index) for index in range(shape[1]))
        else:
            columns = ("Value",)
        rows = len(value) if self._sequence(value) else 1
        return DataSection(name, columns, rows)

    @staticmethod
    def _sequence(value: Any) -> bool:
        return not isinstance(value, (str, bytes)) and hasattr(value, "__len__") and (
            not hasattr(value, "ndim") or value.ndim > 0
        )

    @staticmethod
    def _text(value: Any) -> str:
        if hasattr(value, "tolist"):
            value = value.tolist()
        if isinstance(value, (list, tuple, dict)):
            return json.dumps(value, ensure_ascii=True, default=str)
        return str(value)

    def page(self, name: str, offset: int, limit: int) -> DataPage:
        if offset < 0 or limit < 1:
            raise ValueError("Invalid data page range")
        section = self._section(name)
        value = self._values[name]
        values = value if self._sequence(value) else [value]
        rows = []
        for row in values[offset:offset + limit]:
            cells = row if len(section.columns) > 1 else [row]
            rows.append(tuple(self._text(cell) for cell in cells))
        return DataPage(section, offset, tuple(rows))

    def records(
        self, cancel: Event | None = None,
    ) -> Generator[tuple[tuple[str, ...], ...], None, None]:
        if self._fields:
            yield from self._series_records(cancel)
            return
        self._values = dict(self._static)
        yield from self._records(tuple(self._static), "", cancel)
        for frame, step in enumerate(self._steps()):
            if cancel is not None and cancel.is_set():
                raise JobCancelled("File loading cancelled")
            sections = self._set_step(step)
            names = tuple(section.name for section in sections if section.name not in self._static)
            yield from self._records(names, f"frames/{frame}/", cancel)

    def _records(
        self, names: tuple[str, ...], prefix: str, cancel: Event | None,
    ) -> Iterator[tuple[tuple[str, ...], ...]]:
        for name in names:
            section = self._section(name)
            for offset in range(0, section.rows, 256):
                if cancel is not None and cancel.is_set():
                    raise JobCancelled("File loading cancelled")
                page = self.page(name, offset, 256)
                yield tuple(
                    (prefix + name, str(offset + index),
                     row[0] if len(row) == 1 else "[" + ", ".join(row) + "]")
                    for index, row in enumerate(page.rows)
                )

    def close(self) -> None:
        try:
            if self._reader is not None:
                self._reader.close()
        finally:
            self._reader = None
            self._universe = None
            self._values.clear()
            self._static.clear()
