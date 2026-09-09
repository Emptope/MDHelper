import struct
from pathlib import Path

import numpy as np
import pytest

from mdhelper.backends.mdanalysis.trajectory import MDAnalysisTrajectorySource
from mdhelper.backends.mdanalysis.workspace import BinaryDocument
from mdhelper.core.system import FrameRange

ROOT = Path(__file__).parents[2]
INPUTS = tuple(sorted((ROOT / "tests" / "data" / "tpr").glob("*.tpr")))


@pytest.mark.parametrize("source", INPUTS, ids=lambda path: path.stem)
def test_run_input_exposes_topology_coordinates_and_box(source: Path) -> None:
    from MDAnalysis import _PARSERS, _READERS
    from MDAnalysis.topology.tpr import setting
    from MDAnalysis.topology.tpr.utils import TPXUnpacker

    from mdhelper.backends.mdanalysis.formats.tpr import read_header

    header = read_header(TPXUnpacker(source.read_bytes()))
    versions = setting.SUPPORTED_VERSIONS
    parser, reader = _PARSERS["TPR"], _READERS["TPR"]
    document = BinaryDocument(source)
    try:
        sections = {item.name: item for item in document.select_frame(0)}
        count = sections["topology/names"].rows
        assert count > 0
        assert sections["positions"].rows == count
        assert ("velocities" in sections) == bool(header.bV)
        if header.bV:
            assert sections["velocities"].rows == count
        assert sections["dimensions"].rows == 6
        assert float(document.page("volume", 0, 1).rows[0][0]) > 0
        last = document.page("positions", count - 1, 1).rows
        assert len(last) == 1
        assert all(np.isfinite(float(cell)) for cell in last[0])
        assert "time" not in sections
        assert "dt" not in sections
    finally:
        document.close()
    assert setting.SUPPORTED_VERSIONS == versions
    assert _PARSERS["TPR"] is parser
    assert _READERS["TPR"] is reader


def test_run_input_can_be_used_as_analysis_input() -> None:
    source = INPUTS[0]
    trajectory = MDAnalysisTrajectorySource(source, source)
    try:
        frames = tuple(trajectory.iter_frames(FrameRange()))
        assert len(frames) == 1
        assert len(frames[0].positions_nm) == len(trajectory.atoms)
        assert frames[0].box.volume_nm3 > 0
    finally:
        trajectory.close()


@pytest.mark.parametrize("source", INPUTS, ids=lambda path: path.stem)
def test_run_input_unit_conversion(source: Path) -> None:
    from mdhelper.backends.mdanalysis.formats.tpr import TprReader

    with TprReader(str(source), convert_units=False) as native:
        with TprReader(str(source)) as converted:
            np.testing.assert_allclose(converted.ts.positions, native.ts.positions * 10)
            np.testing.assert_allclose(converted.ts.velocities, native.ts.velocities * 10)
            np.testing.assert_allclose(converted.ts.dimensions[:3], native.ts.dimensions[:3] * 10)
            np.testing.assert_allclose(converted.ts.dimensions[3:], native.ts.dimensions[3:])


def test_previously_supported_run_input_matches_upstream() -> None:
    from MDAnalysis.coordinates.TPR import TPRReader
    from MDAnalysis.topology.tpr import setting
    from MDAnalysis.topology.tpr.utils import TPXUnpacker
    from MDAnalysis.topology.TPRParser import TPRParser

    from mdhelper.backends.mdanalysis.formats.tpr import TprReader, read_header, read_topology

    checked = 0
    for source in INPUTS:
        if read_header(TPXUnpacker(source.read_bytes())).fver not in setting.SUPPORTED_VERSIONS:
            continue
        topology, *_ = read_topology(str(source))
        with TPRParser(str(source)) as parser:
            reference = parser.parse()
        assert topology.n_atoms == reference.n_atoms
        for attribute in reference.attrs:
            if hasattr(attribute, "values"):
                np.testing.assert_array_equal(
                    getattr(topology, attribute.attrname).values, attribute.values,
                )
        with TPRReader(str(source), convert_units=False) as upstream:
            with TprReader(str(source), convert_units=False) as local:
                np.testing.assert_array_equal(local.ts.positions, upstream.ts.positions)
                np.testing.assert_array_equal(local.ts.velocities, upstream.ts.velocities)
        checked += 1
    assert checked


@pytest.mark.parametrize("length", [0, 32, -100])
def test_truncated_run_input_is_rejected(tmp_path: Path, length: int) -> None:
    source = tmp_path / "truncated.tpr"
    source.write_bytes(INPUTS[0].read_bytes()[:length])
    with pytest.raises((EOFError, ValueError, OSError)):
        BinaryDocument(source)


def test_unknown_run_input_version_remains_rejected(tmp_path: Path) -> None:
    from MDAnalysis.topology.tpr.utils import TPXUnpacker

    data = bytearray(INPUTS[0].read_bytes())
    header = TPXUnpacker(data)
    header.do_string()
    header.unpack_int()
    struct.pack_into(">i", data, header.get_position(), 2**30)
    source = tmp_path / "unknown.tpr"
    source.write_bytes(data)
    with pytest.raises((NotImplementedError, ValueError)):
        BinaryDocument(source)
