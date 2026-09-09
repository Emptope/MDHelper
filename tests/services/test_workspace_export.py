from __future__ import annotations

import csv
from pathlib import Path
from threading import Event

import pytest

from mdhelper.core.errors import ConfigurationError, JobCancelled
from mdhelper.core.workspace import DataLayout
from mdhelper.services.workspace import export_workspace_data


@pytest.fixture
def binary(tmp_path: Path, monkeypatch):
    source = tmp_path / "data.bin"
    source.write_bytes(b"\0original")
    closed = []
    rows = [("data", str(i), f'value {i},\t"quoted"\n{chr(20013)}') for i in range(601)]

    class Reader:
        layout = DataLayout()

        def __init__(self, _path):
            pass

        def records(self, _cancel):
            for row in rows:
                yield (row,)

        def close(self):
            closed.append(True)

    monkeypatch.setattr("mdhelper.backends.mdanalysis.workspace.BinaryDocument", Reader)
    return source, rows, closed, Reader


@pytest.mark.parametrize("suffix,delimiter", [("csv", ","), ("CSV", ","), ("txt", "\t")])
def test_export_all_records_not_just_preview_page(
    binary, tmp_path: Path, suffix, delimiter,
) -> None:
    source, rows, closed, _reader = binary
    target = tmp_path / f"exported data.{suffix}"
    assert export_workspace_data(source, target) == target
    with target.open(encoding="utf-8", newline="") as handle:
        actual = list(csv.reader(handle, delimiter=delimiter))
    assert actual == [list(DataLayout().columns), *[list(row) for row in rows]]
    assert closed == [True]
    assert source.read_bytes() == b"\0original"
    assert not list(tmp_path.glob(".*.tmp"))


@pytest.mark.parametrize("suffix", ["tsv", "json"])
def test_export_rejects_unsupported_format(binary, tmp_path: Path, suffix: str) -> None:
    source, _rows, _closed, _reader = binary
    target = tmp_path / f"previous.{suffix}"
    target.write_text("previous", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="Export format must be CSV"):
        export_workspace_data(source, target)
    assert target.read_text(encoding="utf-8") == "previous"
    assert not list(tmp_path.glob(".*.tmp"))


@pytest.mark.parametrize("failure", ["cancel", "reader", "replace"])
def test_export_failure_keeps_existing_destination(binary, tmp_path: Path, monkeypatch, failure):
    source, rows, closed, reader = binary
    target = tmp_path / "existing.txt"
    target.write_text("old export", encoding="utf-8")
    cancel = Event()

    def records(self, _cancel):
        for index, row in enumerate(rows):
            if index == 300:
                if failure == "cancel":
                    cancel.set()
                elif failure == "reader":
                    raise OSError("Truncated binary input")
            yield (row,)

    monkeypatch.setattr(reader, "records", records)
    if failure == "replace":
        def reject(*_args):
            raise OSError("Destination not writable")
        monkeypatch.setattr("mdhelper.services.workspace.export.os.replace", reject)
    with pytest.raises(JobCancelled if failure == "cancel" else OSError):
        export_workspace_data(source, target, cancel)
    assert closed == [True]
    assert target.read_text(encoding="utf-8") == "old export"
    assert source.read_bytes() == b"\0original"
    assert not list(tmp_path.glob(".*.tmp"))


@pytest.mark.parametrize("alias", ["same", "symlink", "hardlink"])
def test_export_never_overwrites_source(binary, tmp_path: Path, alias: str) -> None:
    source, _rows, _closed, _reader = binary
    target = source if alias == "same" else tmp_path / "alias.txt"
    if alias == "symlink":
        target.symlink_to(source)
    elif alias == "hardlink":
        target.hardlink_to(source)
    with pytest.raises(ConfigurationError, match="overwrite the source"):
        export_workspace_data(source, target)
    assert source.read_bytes() == b"\0original"


def test_export_rejects_unparsed_file(tmp_path: Path) -> None:
    source = tmp_path / "plain.txt"
    source.write_text("editable", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="no parsed data"):
        export_workspace_data(source, tmp_path / "export.txt")
    assert not (tmp_path / "export.txt").exists()


@pytest.mark.parametrize("columns", [(), (-1,), (3,), (0, 0)])
def test_invalid_export_columns_leave_destination_untouched(binary, tmp_path: Path, columns):
    source, _rows, _closed, _reader = binary
    target = tmp_path / "existing.txt"
    target.write_text("previous", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="Invalid export columns"):
        export_workspace_data(source, target, columns=columns)
    assert target.read_text(encoding="utf-8") == "previous"
    assert not list(tmp_path.glob(".*.tmp"))


def test_energy_export_rejects_frame_and_time_without_a_term(tmp_path: Path) -> None:
    from tests.support.energy import write_energy

    source = tmp_path / "energy.edr"
    write_energy(source, {"Time": [0, 1], "signal": [5, 6]}, {"signal": "kJ/mol"})
    target = tmp_path / "energy.txt"
    with pytest.raises(ConfigurationError, match="at least one term"):
        export_workspace_data(source, target, columns=(0, 1))
    assert not target.exists()


def test_energy_export_contains_last_frame_and_column_names(tmp_path: Path) -> None:
    from tests.support.energy import write_energy

    source = tmp_path / "energy.edr"
    write_energy(
        source, {"Time": list(range(300)), "signal": list(range(300))}, {"signal": "kJ/mol"},
    )
    target = export_workspace_data(source, tmp_path / "energy.txt")
    with target.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle, delimiter="\t"))
    assert len(rows) == 301
    assert rows[-1] == ["299", "299.0", "299.0"]
    assert "signal" in rows[0][-1]
