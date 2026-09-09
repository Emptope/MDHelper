from pathlib import Path
from sqlite3 import ProgrammingError
from threading import Event

import numpy as np
import pytest

from mdhelper.backends.mdanalysis.workspace import BinaryDocument
from mdhelper.core.errors import JobCancelled
from mdhelper.core.workspace import DataLayout
from mdhelper.services.workspace import WorkspaceDocument


def test_missing_box_is_not_reported_as_zero_volume(tmp_path: Path) -> None:
    import MDAnalysis as mda

    path = tmp_path / "coordinates.trr"
    universe = mda.Universe.empty(2, trajectory=True)
    universe.atoms.positions = np.ones((2, 3))
    universe.trajectory.ts.time = 7
    with mda.Writer(str(path), n_atoms=2) as writer:
        writer.write(universe)
    document = BinaryDocument(path)
    try:
        sections = {section.name for section in document.select_frame(0)}
        assert "dimensions" not in sections
        assert "volume" not in sections
        assert document.page("time", 0, 1).rows == (("7.0",),)
        cancel = Event()
        cancel.set()
        with pytest.raises(JobCancelled):
            list(document.records(cancel))
    finally:
        document.close()


@pytest.mark.parametrize("failure", [ValueError("corrupt record"), JobCancelled("cancelled")])
def test_partial_reads_close_reader_and_disk_store(tmp_path: Path, monkeypatch, failure) -> None:
    from mdhelper.io.workspace import DataStore

    path = tmp_path / "data.bin"
    path.write_bytes(b"\0")
    closed = []
    stores = []

    class Reader:
        layout = DataLayout()

        def __init__(self, _path):
            pass

        def records(self, _cancel):
            yield (("data", "0", "1"),)
            raise failure

        def close(self):
            closed.append(True)

    def store(columns):
        result = DataStore(columns)
        stores.append(result)
        return result

    monkeypatch.setattr("mdhelper.backends.mdanalysis.workspace.BinaryDocument", Reader)
    monkeypatch.setattr("mdhelper.services.workspace.document.DataStore", store)
    with WorkspaceDocument(path) as document:
        assert document.file.parsed
        assert not closed
        with pytest.raises(type(failure)):
            document.page(0)
        assert document.rows == 0
    assert closed == [True]
    assert stores
    with pytest.raises(ProgrammingError):
        stores[0].page(0, 1)
