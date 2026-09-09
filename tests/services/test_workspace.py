from __future__ import annotations

import warnings
from pathlib import Path
from threading import Event

import numpy as np
import pytest

from mdhelper.core.errors import ConfigurationError, JobCancelled
from mdhelper.services.workspace import WorkspaceDocument, open_workspace_file


def test_small_text_detection_preserves_utf8_boundaries(tmp_path: Path) -> None:
    path = tmp_path / "text.dat"
    text = "a" * 65535 + chr(233) + "b" * 8192
    path.write_text(text, encoding="utf-8")
    file = open_workspace_file(path)
    assert file.editable
    assert file.text == text


def test_binary_document_exposes_all_frames_and_rows(tmp_path: Path) -> None:
    import MDAnalysis as mda

    path = tmp_path / "data.trr"
    count = 257
    universe = mda.Universe.empty(count, trajectory=True, velocities=True, forces=True)
    universe.dimensions = [30, 40, 50, 90, 90, 90]
    with mda.Writer(str(path), n_atoms=count) as writer:
        for frame in range(3):
            universe.atoms.positions = np.arange(count * 3).reshape(count, 3) + frame
            universe.atoms.velocities = frame + 2
            universe.atoms.forces = frame + 3
            universe.trajectory.ts.time = frame * 5
            writer.write(universe)
    with WorkspaceDocument(path) as document:
        assert document.file.parsed and not document.file.editable
        rows = all_rows(document)
        frame_numbers = [int(row[0].split("/")[1]) for row in rows
                         if row[0].startswith("frames/")]
        assert frame_numbers == sorted(frame_numbers)
        assert set(frame_numbers) == set(range(3))
        positions = [row for row in rows if row[0] == "frames/2/positions"]
        assert len(positions) == count
        assert float(positions[-1][-1].strip("[]").split(",")[-1]) == pytest.approx(count * 3 + 1)
        for name, expected in (("velocities", 4), ("forces", 5)):
            row = next(row for row in rows if row[0] == f"frames/2/{name}")
            assert float(row[-1].strip("[]").split(",")[-1]) == pytest.approx(expected)
        assert next(row[-1] for row in rows if row[0] == "frames/2/time") == "10.0"
    assert not list(tmp_path.glob(".*offset*"))


def test_unsupported_and_missing_files(tmp_path: Path) -> None:
    path = tmp_path / "unknown.bin"
    path.write_bytes(b"\x00\xff")
    with WorkspaceDocument(path) as document:
        assert not document.file.parsed
        assert not document.file.editable
        assert document.rows == 0
        with pytest.raises(ConfigurationError):
            document.page(0)
    with pytest.raises(ConfigurationError):
        open_workspace_file(tmp_path / "missing")


def test_cancelled_text_and_invalid_utf8(tmp_path: Path) -> None:
    path = tmp_path / "data"
    path.write_bytes(b"text")
    cancel = Event()
    cancel.set()
    with pytest.raises(JobCancelled):
        WorkspaceDocument(path, cancel)
    path.write_bytes(b"text\xff")
    assert not open_workspace_file(path).editable
    path.write_bytes(b"\0")
    with pytest.raises(JobCancelled):
        WorkspaceDocument(path, cancel)


def test_topology_properties_and_connectivity_are_not_truncated(tmp_path: Path) -> None:
    import MDAnalysis as mda

    from mdhelper.backends.mdanalysis.workspace import BinaryDocument

    count = 257
    universe = mda.Universe.empty(count, trajectory=True)
    names = [f"A{index % 100}" for index in range(count)]
    universe.add_TopologyAttr("names", names)
    for attr, values in {
        "altLocs": [""] * count,
        "resnames": ["MOL"],
        "icodes": [""],
        "segids": ["SYSTEM"],
        "chainIDs": ["A"] * count,
        "resids": [1],
        "occupancies": [1.0] * count,
        "tempfactors": [0.0] * count,
        "elements": ["C"] * count,
        "record_types": ["ATOM"] * count,
        "formalcharges": [0] * count,
    }.items():
        universe.add_TopologyAttr(attr, values)
    universe.dimensions = [30, 40, 50, 90, 90, 90]
    universe.add_TopologyAttr("bonds", [(index, index + 1) for index in range(count - 1)])
    path = tmp_path / "topology.pdb"
    universe.atoms.write(str(path))
    document = BinaryDocument(path)
    try:
        sections = {section.name: section for section in document.select_frame(0)}
        assert "time" not in sections
        assert "dt" not in sections
        assert sections["topology/names"].rows == count
        assert document.page("topology/names", count - 1, 1).rows == ((names[-1],),)
        bonds = document.page("topology/bonds", count - 2, 1)
        assert str(count - 1) in bonds.rows[-1][-1]
        with pytest.raises(IndexError):
            document.select_frame(document.frames)
        document.select_frame(0)
        with pytest.raises(ValueError):
            document.page("positions", -1, 1)
        assert document.page("positions", count, 1).rows == ()
    finally:
        document.close()
    path.unlink()


def test_energy_reader_exposes_every_term_and_sample(tmp_path: Path) -> None:
    import pyedr

    from tests.support.energy import write_energy

    path = tmp_path / "energy.edr"
    frames = 259
    data = {"Time": np.arange(frames) * 2.0}
    data.update({f"term_{index}": np.arange(frames) + index for index in range(257)})
    units = dict(zip(data, ("ps", *("bar", "nm", "K", "", "nm^3", "kg/m^3") * 43), strict=False))
    write_energy(path, data, units)
    reference = pyedr.edr_to_dict(str(path))
    for name in data:
        np.testing.assert_allclose(reference[name], data[name])
    with warnings.catch_warnings(record=True, action="always") as captured, \
            WorkspaceDocument(path) as document:
        assert document.file.parsed
        assert document.rows == 0
        rows = all_rows(document)
        assert document.rows == frames
        layout = document.file.layout
        assert len(layout.columns) == len(data) + 1
        assert layout.selectable == tuple(range(2, len(data) + 1))
        for column, (name, values) in enumerate(data.items(), 1):
            assert name in layout.columns[column]
            if units[name]:
                assert units[name] in layout.columns[column]
            for frame, value in enumerate(values):
                assert int(rows[frame][0]) == frame
                assert float(rows[frame][column]) == value
        assert document.page(frames, 1).rows == ()
    assert not captured


def all_rows(document: WorkspaceDocument) -> list[tuple[str, ...]]:
    rows = []
    while True:
        page = document.page(len(rows), 128)
        rows.extend(page.rows)
        if page.complete:
            return rows
