# SPDX-License-Identifier: LGPL-2.1-or-later
# Portions copyright (c) 2006-2017 The MDAnalysis Development Team and contributors.
# Portions copyright (c) 2011 Zhuyi Xue.

"""Strict run-input decoding with shared topology and coordinate traversal.

Decoder provenance and license terms are documented in docs/TPR.md.
"""

from __future__ import annotations

from typing import Any, ClassVar

import numpy as np
from MDAnalysis.coordinates.base import SingleFrameReaderBase
from MDAnalysis.core.topologyattrs import Resnums
from MDAnalysis.lib.mdamath import triclinic_box
from MDAnalysis.lib.util import openany
from MDAnalysis.topology.base import TopologyReaderBase
from MDAnalysis.topology.tpr import obj, setting, utils

SUPPORTED_VERSIONS = frozenset((*setting.SUPPORTED_VERSIONS, 138))


def read_header(data: Any) -> Any:
    version_string = data.do_string()
    if not version_string.startswith(b"VERSION"):
        raise ValueError("Invalid run-input header")
    precision = data.unpack_int()
    utils.define_unpack_real(precision, data)
    version = data.unpack_int()
    if version not in SUPPORTED_VERSIONS:
        raise NotImplementedError(f"Unsupported run-input format version: {version}")
    if 77 <= version <= 79:
        data.unpack_int()
        data.do_string()
    generation = data.unpack_int() if version >= 26 else 0
    tag = data.do_string() if version >= 81 else setting.TPX_TAG_RELEASE
    atoms = data.unpack_int()
    groups = data.unpack_int() if version >= 28 else 0
    if atoms < 0 or groups < 0:
        raise ValueError("Negative run-input record count")
    if version < 62:
        data.unpack_int()
        data.unpack_real()
    state = data.unpack_int() if version >= 79 else 0
    coupling = data.unpack_real()
    flags = tuple(data.unpack_int() for _ in range(6))
    if any(flag not in (0, 1) for flag in flags):
        raise ValueError("Invalid run-input presence flags")
    size = None
    if version >= setting.tpxv_AddSizeField and generation >= 27:
        size = data.unpack_int64()
    return obj.TpxHeader(
        version_string, precision, version, generation, tag, atoms, groups,
        state, coupling, *flags, size,
    )


def read_topology(filename: str, resid_from_one: bool = True) -> tuple[Any, Any, Any, Any]:
    with openany(filename, mode="rb") as handle:
        data = utils.TPXUnpacker(handle.read())
    header = read_header(data)
    if header.sizeOfTprBody is not None:
        actual = len(data.get_buffer()) - data.get_position()
        size = header.sizeOfTprBody
        padding = actual - size
        if size < 0 or padding not in (0, (-size) % 4):
            raise ValueError("Run-input body size does not match its header")
        if padding and any(data.get_buffer()[-padding:]):
            raise ValueError("Invalid run-input body padding")
        data = utils.TPXUnpacker2020.from_unpacker(data)
    box = utils.extract_box_info(data, header.fver).size if header.bBox else None
    if header.ngtc:
        if header.fver < 69:
            utils.ndo_real(data, header.ngtc)
        utils.ndo_real(data, header.ngtc)
    if not header.bTop:
        raise ValueError("Run-input file has no topology")
    topology = utils.do_mtop(
        data, header.fver, tpr_resid_from_one=resid_from_one, precision=header.precision,
    )
    if topology.n_atoms != header.natoms:
        raise ValueError("Run-input topology atom count does not match its header")
    topology.add_TopologyAttr(Resnums(topology.resids.values.copy()))
    return topology, header, data, box


class TprParser(TopologyReaderBase):
    format: tuple[str, ...] = ()

    def parse(self, tpr_resid_from_one: bool = True, **_kwargs: Any) -> Any:
        return read_topology(self.filename, tpr_resid_from_one)[0]


class TprReader(SingleFrameReaderBase):
    format: tuple[str, ...] = ()
    units: ClassVar[dict[str, str]] = {
        "length": "nm", "velocity": "nm/ps", "force": "kJ/(mol*nm)",
    }

    def _read_first_frame(self) -> None:
        _topology, header, data, box = read_topology(self.filename)
        self.n_atoms = header.natoms
        self.ts = self._Timestep(
            self.n_atoms, positions=bool(header.bX), velocities=bool(header.bV),
            forces=bool(header.bF), **self._ts_kwargs,
        )
        self.ts.frame = 0
        for present, name, convert in (
            (header.bX, "positions", self.convert_pos_from_native),
            (header.bV, "velocities", self.convert_velocities_from_native),
            (header.bF, "forces", self.convert_forces_from_native),
        ):
            if present:
                values = np.asarray(utils.ndo_rvec(data, self.n_atoms), dtype=np.float32)
                if self.convert_units:
                    convert(values)
                setattr(self.ts, name, values)
        if box is not None:
            vectors = np.asarray(box, dtype=np.float32)
            if self.convert_units:
                self.convert_pos_from_native(vectors)
            self.ts.dimensions = triclinic_box(*vectors)
