from __future__ import annotations

import csv
from pathlib import Path
from threading import Event

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from mdhelper.core.errors import JobCancelled
from mdhelper.gui.workspace.editor import WorkspaceEditor
from tests.support.energy import write_energy
from tests.support.qt import wait_until


@pytest.fixture
def parsed_editor(tmp_path: Path):
    QApplication.instance() or QApplication([])
    source = tmp_path / "energy.edr"
    write_energy(
        source,
        {
            "Time": list(range(300)), "signal": list(range(300)),
            "Temperature": [i + 300 for i in range(300)],
            "Pressure": [i + 600 for i in range(300)],
        },
        {"signal": "kJ/mol", "Temperature": "K", "Pressure": "bar"},
    )
    editor = WorkspaceEditor()
    editor.set_root(tmp_path)
    editor.show()
    editor.open_path(str(source))
    try:
        wait_until(lambda: editor.current_path == str(source) and not editor.data.model.loading)
        yield editor, source
    finally:
        editor.shutdown()
        editor.close()


@pytest.mark.parametrize("suffix,delimiter", [("csv", ","), ("txt", "\t")])
def test_export_action_writes_all_rows_and_preserves_preview(
    parsed_editor, tmp_path: Path, monkeypatch, suffix, delimiter,
):
    editor, source = parsed_editor
    target = tmp_path / f"all rows.{suffix}"

    def choose(_parent, _title, suggested, filters):
        assert suggested == f"{source}.csv"
        assert filters == "CSV files (*.csv);;Text files (*.txt)"
        return str(target), ""

    monkeypatch.setattr(QFileDialog, "getSaveFileName", choose)
    before = editor.data.model.rowCount()
    assert editor.export_button.isVisible()
    assert not editor.save_button.isVisible()
    editor.export_button.click()
    assert not editor.export_button.isEnabled()
    wait_until(lambda: not editor._exporting)
    with target.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle, delimiter=delimiter))
    assert len(rows) == 301
    assert rows[0] == ["Frame", "Time (ps)", "signal (kJ/mol)"]
    assert rows[-1] == ["299", "299.0", "299.0"]
    assert editor.current_path == str(source)
    assert editor.content.currentWidget() is editor.data
    assert editor.data.model.rowCount() == before
    assert editor.export_button.isEnabled()
    assert "Exported:" in editor.status.text()
    editor.clear()
    assert not editor.export_button.isVisible()


@pytest.mark.parametrize("suffix,selected_filter", [
    ("csv", "CSV files (*.csv)"), ("txt", "Text files (*.txt)"),
])
def test_export_appends_missing_extension(parsed_editor, tmp_path: Path, monkeypatch,
                                          suffix, selected_filter):
    editor, _source = parsed_editor
    target = tmp_path / "exported"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", lambda *_: (str(target), selected_filter),
    )
    editor.export_text()
    wait_until(lambda: not editor._exporting)
    assert target.with_suffix(f".{suffix}").exists()
    assert not target.exists()


@pytest.mark.parametrize("answer", [QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No])
def test_appended_extension_requires_overwrite_confirmation(
    parsed_editor, tmp_path: Path, monkeypatch, answer,
):
    editor, _source = parsed_editor
    target = tmp_path / "existing.csv"
    target.write_text("previous", encoding="utf-8")
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        lambda *_: (str(target.with_suffix("")), "CSV files (*.csv)"),
    )
    monkeypatch.setattr(QMessageBox, "question", lambda *_: answer)
    editor.export_text()
    wait_until(lambda: not editor._exporting)
    declined = answer == QMessageBox.StandardButton.No
    assert (target.read_text(encoding="utf-8") == "previous") == declined


@pytest.mark.parametrize("failure", ["cancel", "error"])
def test_export_failure_keeps_preview_usable(parsed_editor, tmp_path: Path, monkeypatch, failure):
    editor, source = parsed_editor
    started = Event()
    errors = []
    editor.error_reported.connect(errors.append)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *_: (str(tmp_path / "out.txt"), ""))

    def export(_source, _target, cancel, _columns):
        started.set()
        if failure == "cancel":
            assert cancel.wait(5)
            raise JobCancelled("Export cancelled")
        raise OSError("Write failed")

    monkeypatch.setattr("mdhelper.gui.workspace.worker.export_workspace_data", export)
    editor.export_text()
    wait_until(started.is_set)
    if failure == "cancel":
        editor.cancel_button.click()
    wait_until(lambda: not editor._exporting)
    assert len(errors) == (0 if failure == "cancel" else 1)
    assert editor.current_path == str(source)
    assert editor.export_button.isEnabled()
    pages = []
    editor.worker.paged.connect(pages.append)
    editor.worker.page(299)
    wait_until(lambda: bool(pages))
    assert pages[-1].rows[0][0] == "299"


@pytest.mark.parametrize("selected", [(1,), (1, 2)])
def test_edr_export_only_checked_terms_including_search_hidden_items(
    parsed_editor, tmp_path: Path, monkeypatch, selected,
):
    editor, _source = parsed_editor
    target = tmp_path / "selected.txt"
    for index in range(editor.data.items.count()):
        editor.data.items.item(index).setCheckState(
            Qt.CheckState.Checked if index in selected else Qt.CheckState.Unchecked,
        )
    editor.data.search.setText("no matching term")
    assert all(editor.data.items.item(i).isHidden() for i in selected)
    assert editor.export_button.isEnabled()
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *_: (str(target), ""))
    editor.export_text()
    # Subsequent selection changes must not change an already submitted export.
    for index in range(editor.data.items.count()):
        editor.data.items.item(index).setCheckState(Qt.CheckState.Unchecked)
    wait_until(lambda: not editor._exporting)
    with target.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle, delimiter="\t"))
    terms = ("signal (kJ/mol)", "Temperature (K)", "Pressure (bar)")
    assert rows[0] == ["Frame", "Time (ps)", *(terms[i] for i in selected)]
    assert rows[-1] == ["299", "299.0", *(str(float(299 + i * 300)) for i in selected)]
    assert len(rows) == 301
    assert all(len(row) == 2 + len(selected) for row in rows)
    assert not editor.export_button.isEnabled()


def test_edr_export_requires_a_checked_term(parsed_editor, monkeypatch):
    editor, _source = parsed_editor
    for index in range(editor.data.items.count()):
        editor.data.items.item(index).setCheckState(Qt.CheckState.Unchecked)

    def unexpected(*_args):
        pytest.fail("Export dialog must not open without a selected term")

    monkeypatch.setattr(QFileDialog, "getSaveFileName", unexpected)
    assert not editor.export_button.isEnabled()
    editor.export_text()
    assert not editor._exporting
    editor.data.items.item(1).setCheckState(Qt.CheckState.Checked)
    assert editor.export_button.isEnabled()


def test_export_dialog_cancel_does_not_start_work(parsed_editor, monkeypatch):
    editor, _source = parsed_editor
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *_: ("", ""))
    status = editor.status.text()
    editor.export_text()
    assert not editor._exporting
    assert editor.status.text() == status
