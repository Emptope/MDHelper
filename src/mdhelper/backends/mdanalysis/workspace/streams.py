"""Sequential adapters that do not build full-file indexes or arrays."""

from __future__ import annotations

import mmap
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from MDAnalysis.coordinates.base import ReaderBase
from MDAnalysis.coordinates.XDR import XDRBaseReader
from pyedr.pyedr import EDRFile, Frame, GMX_Unpacker


class SequentialXdr(XDRBaseReader):
    sequential = True

    def __init__(self, filename: str, **kwargs: Any):
        ReaderBase.__init__(self, filename, **kwargs)
        self._kwargs["dt"] = None
        self._sub = None
        self._xdr = self._file(filename)
        self.n_atoms = self._xdr.n_atoms
        self._frame = -1
        self.ts = self._Timestep(self.n_atoms, **self._ts_kwargs)
        try:
            self._advance()
        except BaseException:
            self._xdr.close()
            raise

    def _advance(self) -> Any:
        frame = self._xdr.read()
        self._frame += 1
        self._frame_to_ts(frame, self.ts)
        return self.ts

    def steps(self) -> Iterator[Any]:
        yield self.ts
        while True:
            try:
                step = self._advance()
            except StopIteration:
                return
            yield step


class EnergyStream(EDRFile):
    sequential = True
    time_selector = "Time"

    def __init__(self, path: str):
        self._handle = Path(path).open("rb")
        try:
            self._mapping = mmap.mmap(self._handle.fileno(), 0, access=mmap.ACCESS_READ)
            try:
                self.data = GMX_Unpacker(self._mapping)
                magic = self.data.unpack_int()
                if magic > 0:
                    count = magic
                else:
                    self.data.unpack_int()
                    count = self.data.unpack_int()
                if count < 0 or count > (len(self._mapping) - self.data.get_position()) // 4:
                    raise ValueError("Energy term count exceeds the file size")
                self.data.set_position(0)
                self.do_enxnms()
                self.unit_dict = {"Time": "ps", **{item.name: item.unit for item in self.nms}}
                self.fields = ("Time", *(item.name for item in self.nms))
                self.auxstep = self._advance()
            except BaseException:
                self._mapping.close()
                raise
        except BaseException:
            self._handle.close()
            raise

    def _advance(self) -> SimpleNamespace:
        if self.data.get_position() == len(self._mapping):
            raise StopIteration
        self.frame = Frame()
        try:
            self.do_enx()
        except EOFError as exc:
            raise OSError("Truncated energy frame") from exc
        if len(self.frame.ener) > len(self.nms):
            raise ValueError("Energy frame has more terms than declared in the header")
        values = {"Time": self.frame.t}
        values.update({name.name: energy.e for name, energy in
                       zip(self.nms, self.frame.ener, strict=False)})
        return SimpleNamespace(data=values, time=self.frame.t)

    def steps(self) -> Iterator[SimpleNamespace]:
        yield self.auxstep
        while True:
            try:
                self.auxstep = self._advance()
            except StopIteration:
                return
            yield self.auxstep

    def close(self) -> None:
        self._mapping.close()
        self._handle.close()
