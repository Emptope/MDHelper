from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest

from mdhelper.backends.mdanalysis.workspace import BinaryDocument
from mdhelper.core.errors import JobCancelled
from mdhelper.core.workspace import DATA_COLUMNS
from mdhelper.services.workspace import WorkspaceDocument


def test_mapping_auxiliary_uses_reader_time_selector_and_units(tmp_path: Path, monkeypatch) -> None:
    from MDAnalysis.auxiliary import core

    closed = []

    class Reader:
        n_steps = 3
        time_selector = "tick"
        def __init__(self, _path):
            self.unit_dict = {"signal": "custom", "tick": "fs"}
            self.auxstep = self[0]

        def __getitem__(self, frame):
            self.auxstep = SimpleNamespace(
                data={"signal": frame + 0.25, "tick": frame * 10}, time=frame * 10,
            )
            return self.auxstep

        def close(self):
            closed.append(True)

    monkeypatch.setattr(core, "get_auxreader_for", lambda *_: Reader)
    path = tmp_path / "samples.binary"
    path.write_bytes(b"\0")
    with WorkspaceDocument(path) as document:
        assert document.file.parsed
        assert document.file.layout.selectable == (2,)
        assert document.rows == 0
        page = document.page(0)
        assert document.rows == Reader.n_steps
        assert page.section.columns == document.file.layout.columns
        assert "tick" in page.section.columns[1]
        assert "fs" in page.section.columns[1]
        assert "custom" in page.section.columns[2]
        assert page.rows == (("0", "0", "0.25"), ("1", "10", "1.25"), ("2", "20", "2.25"))
    assert closed == [True]
    reader = BinaryDocument(path)
    try:
        cancel = Event()
        cancel.set()
        with pytest.raises(JobCancelled):
            list(reader.records(cancel))
    finally:
        reader.close()
    assert closed == [True, True]


def test_non_mapping_auxiliary_keeps_complete_record_view(tmp_path: Path) -> None:
    path = tmp_path / "series.xvg"
    path.write_text("0 4 5\n2 6 7\n", encoding="ascii")
    reader = BinaryDocument(path)
    try:
        assert reader.layout.columns == DATA_COLUMNS
        assert not reader.layout.selectable
        rows = [row for batch in reader.records() for row in batch]
        assert tuple(row[-1] for row in rows if row[0] == "frames/1/data") == (
            "2.0", "6.0", "7.0",
        )
    finally:
        reader.close()
