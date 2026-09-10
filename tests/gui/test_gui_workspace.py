from __future__ import annotations

import os
from pathlib import Path
from threading import Event

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QModelIndex, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QMessageBox, QPushButton

from mdhelper.core.workspace import DATA_COLUMNS, DataPage, DataSection, WorkspaceFile
from mdhelper.gui.controllers.session_state import SessionPhase
from mdhelper.gui.dialogs.projects import NewProjectDialog
from mdhelper.gui.window import MainWindow
from mdhelper.gui.workspace.data import DataModel, DataView
from mdhelper.gui.workspace.editor import WorkspaceEditor
from mdhelper.gui.workspace.worker import DocumentWorker
from tests.support.qt import fetch_all, wait_until

pytestmark = pytest.mark.usefixtures("immediate_integration_detection")


def test_folder_tree_and_dirty_file_transitions(tmp_path: Path, monkeypatch) -> None:
    QApplication.instance() or QApplication([])
    folder = tmp_path / "nested"
    folder.mkdir()
    first = folder / "first.txt"
    second = folder / "second.txt"
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")
    editor = WorkspaceEditor()
    try:
        assert editor.stack.currentWidget() is editor.empty
        assert editor.set_root(tmp_path)
        assert editor.stack.currentWidget() is editor.splitter
        assert editor.tree.isColumnHidden(1)
        root = editor.files.index(str(folder))
        editor.tree.expand(root)
        editor.files.fetchMore(root)
        wait_until(lambda: editor.files.rowCount(root) == 2)
        editor.tree.setCurrentIndex(editor.files.index(str(first)))
        wait_until(lambda: editor.current_path == str(first))
        assert editor.editor.toPlainText() == first.read_text(encoding="utf-8")
        editor.editor.insertPlainText("changed")
        monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Cancel)
        editor.tree.setCurrentIndex(editor.files.index(str(second)))
        assert Path(editor.files.filePath(editor.tree.currentIndex())) == first
        assert not editor.set_root(None)
        assert editor.root == tmp_path
        monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Save)
        expected = editor.editor.toPlainText()
        assert editor.open_path(str(second))
        wait_until(lambda: editor.current_path == str(second))
        assert first.read_text(encoding="utf-8") == expected
        editor.editor.insertPlainText("discard")
        monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Discard)
        assert editor.set_root(None)
        assert second.read_text(encoding="utf-8") == "second"
        assert editor.current_path is None
        assert not editor.save()
        with pytest.raises(NotADirectoryError):
            editor.set_root(first)
    finally:
        editor.shutdown()
        editor.close()


def test_long_file_details_do_not_squeeze_the_folder_tree(tmp_path: Path) -> None:
    from PySide6.QtGui import QFont

    QApplication.instance() or QApplication([])
    editor = WorkspaceEditor()
    editor.setFont(QFont(editor.font().family(), 14))
    editor.resize(880, 650)
    path = tmp_path / ("long-name-" * 18 + ".bin")
    path.write_bytes(b"\0")
    error = "Unsupported binary data: " + "format detail " * 80
    try:
        editor.set_root(tmp_path)
        editor.show()
        QTest.qWait(20)
        before = editor.splitter.sizes()[0]
        width = editor.width()
        editor.set_file(WorkspaceFile(str(path), "", False, False, error))
        QTest.qWait(20)
        assert editor.width() == width
        assert editor.splitter.sizes()[0] >= before
        assert editor.minimumSizeHint().width() <= width
        assert error in editor.status.toolTip()
        assert str(path) in editor.info.toolTip()
    finally:
        editor.shutdown()
        editor.close()


@pytest.mark.parametrize("editable,parsed", [(True, False), (False, True), (False, False)])
def test_file_name_above_content_and_metadata_below(
    tmp_path: Path, monkeypatch, editable: bool, parsed: bool,
) -> None:
    from datetime import datetime
    from types import SimpleNamespace

    from PySide6.QtCore import QPoint

    QApplication.instance() or QApplication([])
    path = tmp_path / "sample.data"
    path.write_bytes(b"sample")
    message = "Reader details"
    monkeypatch.setattr(
        "mdhelper.gui.workspace.worker.WorkspaceDocument",
        lambda source, _cancel: SimpleNamespace(
            file=WorkspaceFile(str(Path(source).resolve()), "sample", editable, parsed, message),
            rows=0, close=lambda: None,
        ),
    )
    editor = WorkspaceEditor()
    try:
        editor.set_root(tmp_path)
        editor.resize(880, 650)
        editor.show()
        editor.open_path(str(path))
        wait_until(lambda: editor.current_path == str(path))
        QTest.qWait(20)
        wait_until(lambda: editor.current_path == str(path))
        content = editor.content
        top = content.mapTo(editor, QPoint(0, 0)).y()
        bottom = content.mapTo(editor, QPoint(0, content.height())).y()
        name_bottom = editor.info.mapTo(editor, QPoint(0, editor.info.height())).y()
        metadata_top = editor.status.mapTo(editor, QPoint(0, 0)).y()
        assert name_bottom <= top < bottom <= metadata_top
        assert editor.info.text() == path.name
        assert editor.info.isVisible() and editor.status.isVisible()
        stat = path.stat()
        modified = datetime.fromtimestamp(stat.st_mtime).isoformat(sep=" ", timespec="seconds")
        assert str(stat.st_size) in editor.status.text()
        assert modified in editor.status.text()
        assert message in editor.status.toolTip()
        assert str(path) in editor.info.toolTip()
        assert content.currentWidget() is (editor.data if parsed else editor.editor)
        assert editor.save_button.isVisible() is editable
        editor.clear()
        assert not editor.info.text()
        assert not editor.info.toolTip()
        assert not editor.status.toolTip()
        assert modified not in editor.status.text()
    finally:
        editor.shutdown()
        editor.close()


def test_saved_file_metadata_refreshes(tmp_path: Path) -> None:
    from datetime import datetime

    QApplication.instance() or QApplication([])
    path = tmp_path / "notes.txt"
    path.write_text("original", encoding="ascii")
    os.utime(path, (1_000_000_000, 1_000_000_000))
    editor = WorkspaceEditor()
    try:
        editor.open_path(str(path))
        wait_until(lambda: editor.current_path == str(path))
        before = editor.status.text()
        editor.editor.insertPlainText("new content")
        expected = editor.editor.toPlainText()
        assert editor.save()
        stat = path.stat()
        modified = datetime.fromtimestamp(stat.st_mtime).isoformat(sep=" ", timespec="seconds")
        assert editor.status.text() != before
        assert modified in editor.status.text()
        assert str(len(expected.encode("utf-8"))) in editor.status.text()
        assert path.read_text(encoding="utf-8") == expected
        assert not editor.editor.document().isModified()
    finally:
        editor.shutdown()
        editor.close()


def test_editor_save_failure_and_load_failure(tmp_path: Path, monkeypatch) -> None:
    QApplication.instance() or QApplication([])
    path = tmp_path / "notes"
    path.write_text("text", encoding="utf-8")
    editor = WorkspaceEditor()
    errors = []
    editor.error_reported.connect(errors.append)
    try:
        editor.open_path(str(path))
        wait_until(lambda: editor.current_path is not None)
        editor.editor.insertPlainText("edit")
        def fail(*_args):
            raise OSError("write failed")
        monkeypatch.setattr("mdhelper.gui.workspace.editor.save_workspace_text", fail)
        monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Save)
        assert not editor.confirm_discard()
        assert errors and editor.editor.document().isModified()
        monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Discard)
        missing = tmp_path / "missing"
        editor.open_path(str(missing))
        assert editor.info.text() == missing.name
        wait_until(lambda: len(errors) == 2)
        assert editor.info.text() == missing.name
        assert str(missing) in editor.info.toolTip()
        assert str(errors[-1]) in editor.status.toolTip()
        assert editor.current_path is None
        assert editor.editor.isReadOnly()
        assert editor.cancel_button.isHidden()
        editor.cancel()
    finally:
        editor.shutdown()
        editor.close()


def test_data_model_scrolls_all_rows_with_bounded_cache() -> None:
    QApplication.instance() or QApplication([])
    view = DataView()
    model = view.model
    requests = []
    model.page_requested.connect(requests.append)
    count = (model.cache_size + 1) * model.page_size
    section = DataSection("data", DATA_COLUMNS, count)
    model.configure(count)
    for offset in range(0, count, model.page_size):
        index = model.index(offset, 2)
        assert model.data(index) is None
        assert requests[-1] == offset
        rows = tuple(("positions", str(row), str(row * 2))
                     for row in range(offset, offset + model.page_size))
        model.set_page(DataPage(section, offset, rows))
        assert model.data(index) == str(offset * 2)
    assert len(model._pages) == model.cache_size
    assert model.data(model.index(0, 2)) is None
    assert requests[-1] == 0
    assert model.rowCount() == count
    assert model.columnCount() == len(DATA_COLUMNS)
    assert model.rowCount(index) == model.columnCount(index) == 0
    assert model.data(QModelIndex()) is None
    assert model.data(index, Qt.ItemDataRole.EditRole) is None
    assert model.headerData(0, Qt.Orientation.Horizontal) == DATA_COLUMNS[0]
    assert model.headerData(count - 1, Qt.Orientation.Vertical) == str(count - 1)
    assert model.headerData(0, Qt.Orientation.Horizontal, Qt.ItemDataRole.EditRole) is None
    model.configure(0)
    assert model.rowCount() == 0
    assert not model._pages
    view.close()


def test_binary_editor_reads_last_page_and_frame(tmp_path: Path) -> None:
    import MDAnalysis as mda

    QApplication.instance() or QApplication([])
    path = tmp_path / "coordinates.trr"
    count = DataModel.page_size + 1
    universe = mda.Universe.empty(count, trajectory=True)
    with mda.Writer(str(path), n_atoms=count) as writer:
        for frame in range(2):
            universe.atoms.positions = frame + 1
            writer.write(universe)
    editor = WorkspaceEditor()
    try:
        editor.open_path(str(path))
        wait_until(lambda: editor.current_path == str(path))
        assert editor.content.currentWidget() is editor.data
        assert editor.editor.isReadOnly()
        assert not editor.save_button.isEnabled()
        model = editor.data.model
        fetch_all(model)
        assert model.rowCount() > count * 2
        index = model.index(model.rowCount() - 1, 2)
        wait_until(lambda: model.data(index) is not None)
        assert float(str(model.data(index)).strip("[]").split(",")[-1]) == pytest.approx(2)
        wait_until(lambda: model.data(model.index(0, 0)) is not None)
        assert str(model.data(model.index(0, 0))).startswith("topology/")
    finally:
        editor.shutdown()
        editor.close()


def test_energy_table_selects_items_without_reloading_frames(tmp_path: Path) -> None:
    import numpy as np

    from tests.support.energy import write_energy

    QApplication.instance() or QApplication([])
    frames = DataModel.page_size + 3
    data = {"Time": np.arange(frames) * 0.5}
    data.update({f"item_{index}": np.arange(frames) + index for index in range(257)})
    units = dict.fromkeys(data, "kJ/mol")
    units["Time"] = "ps"
    path = tmp_path / "series.edr"
    write_energy(path, data, units)
    editor = WorkspaceEditor()
    try:
        editor.open_path(str(path))
        wait_until(lambda: editor.current_path == str(path))
        view = editor.data
        model = view.model
        fetch_all(model)
        assert model.rowCount() == frames
        assert view.items.count() == len(data) - 1
        assert not view.selector.isHidden()
        assert not view.table.isColumnHidden(0)
        assert not view.table.isColumnHidden(1)
        generation = editor.worker._generation
        last = view.items.item(view.items.count() - 1)
        last.setCheckState(Qt.CheckState.Checked)
        column = last.data(Qt.ItemDataRole.UserRole)
        assert not view.table.isColumnHidden(column)
        view.search.setText(last.text())
        assert not last.isHidden()
        assert view.items.item(0).isHidden()
        view.search.clear()
        assert not view.items.item(0).isHidden()
        index = model.index(frames - 1, column)
        wait_until(lambda: model.data(index) is not None)
        assert float(model.data(index)) == data[last.text().split(" (")[0]][-1]
        assert float(model.data(model.index(frames - 1, 1))) == data["Time"][-1]
        first = view.items.item(0)
        first.setCheckState(Qt.CheckState.Unchecked)
        assert view.table.isColumnHidden(first.data(Qt.ItemDataRole.UserRole))
        assert editor.worker._generation == generation
        assert model.rowCount() == frames
        assert not editor.save_button.isEnabled()
        text = tmp_path / "notes.txt"
        text.write_text("notes", encoding="ascii")
        editor.open_path(str(text))
        wait_until(lambda: editor.current_path == str(text))
        assert view.items.count() == 0
        assert view.selector.isHidden()
    finally:
        editor.shutdown()
        editor.close()


def test_worker_cancellation_suppresses_stale_results(tmp_path: Path, monkeypatch) -> None:
    QApplication.instance() or QApplication([])
    entered, release = Event(), Event()
    closed = []
    class Document:
        def __init__(self, path, _cancel):
            self.path = path
            self.file = WorkspaceFile(path, path, True, False, "")
            self.rows = 0
            if path == str(tmp_path / "first"):
                entered.set()
                release.wait(10)
        def close(self):
            closed.append(self.path)
    monkeypatch.setattr("mdhelper.gui.workspace.worker.WorkspaceDocument", Document)
    worker = DocumentWorker()
    opened = []
    worker.opened.connect(opened.append)
    first, second = str(tmp_path / "first"), str(tmp_path / "second")
    try:
        worker.open(first)
        assert entered.wait(5)
        worker.open(second)
        release.set()
        wait_until(lambda: len(opened) == 1)
        assert opened[0][0].path == second
        assert first in closed
        worker.cancel()
        worker.shutdown()
        assert second in closed
        worker.open(first)
        worker.shutdown()
    finally:
        release.set()
        worker.shutdown()


def test_workspace_navigation_cancels_read_and_resumes(tmp_path: Path, monkeypatch) -> None:
    from mdhelper.gui.pages.workspace import WorkspaceTabs

    QApplication.instance() or QApplication([])
    entered, release = Event(), Event()
    cancelled = []
    closed = []

    class Document:
        def __init__(self, path, cancel):
            self.file = WorkspaceFile(path, "", False, True, "Data")
            self.rows = 1
            if not entered.is_set():
                entered.set()
                release.wait(10)
                cancelled.append(cancel.is_set())

        def close(self):
            closed.append(True)

    path = tmp_path / "data.bin"
    path.write_bytes(b"\0")
    monkeypatch.setattr("mdhelper.gui.workspace.worker.WorkspaceDocument", Document)
    tabs = WorkspaceTabs()
    try:
        tabs.editor.open_path(str(path))
        assert entered.wait(5)
        tabs.setCurrentWidget(tabs.load)
        release.set()
        wait_until(lambda: bool(cancelled))
        assert cancelled == [True]
        wait_until(lambda: bool(closed))
        assert tabs.editor.current_path is None
        tabs.setCurrentWidget(tabs.editor)
        wait_until(lambda: tabs.editor.current_path == str(path))
        assert tabs.editor.data.model.rowCount() == 1
        tabs.setCurrentWidget(tabs.analysis)
        wait_until(lambda: len(closed) == 2)
        assert tabs.editor.data.model.rowCount() == 0
        tabs.setCurrentWidget(tabs.editor)
        wait_until(lambda: tabs.editor.data.model.rowCount() == 1)
    finally:
        release.set()
        tabs.editor.shutdown()
        tabs.close()


def test_workspace_navigation_preserves_dirty_text(tmp_path: Path) -> None:
    from mdhelper.gui.pages.workspace import WorkspaceTabs

    QApplication.instance() or QApplication([])
    path = tmp_path / "notes.txt"
    path.write_text("original", encoding="ascii")
    tabs = WorkspaceTabs()
    try:
        tabs.editor.open_path(str(path))
        wait_until(lambda: tabs.editor.current_path == str(path))
        tabs.editor.editor.insertPlainText("edit")
        expected = tabs.editor.editor.toPlainText()
        tabs.setCurrentWidget(tabs.load)
        tabs.setCurrentWidget(tabs.editor)
        assert tabs.editor.editor.toPlainText() == expected
        assert tabs.editor.editor.document().isModified()
        assert path.read_text(encoding="ascii") == "original"
    finally:
        tabs.editor.shutdown()
        tabs.close()


def test_worker_page_failure_closes_document(monkeypatch) -> None:
    QApplication.instance() or QApplication([])
    closed = []

    class Document:
        def __init__(self, path, _cancel):
            self.file = WorkspaceFile(path, "", False, True, "Data")
            self.rows = 1

        def page(self, _offset):
            raise OSError("Read failed")

        def close(self):
            closed.append(True)

    monkeypatch.setattr("mdhelper.gui.workspace.worker.WorkspaceDocument", Document)
    worker = DocumentWorker()
    opened, errors = [], []
    worker.opened.connect(opened.append)
    worker.failed.connect(errors.append)
    try:
        worker.open("data.bin")
        wait_until(lambda: bool(opened))
        worker.page(0)
        wait_until(lambda: bool(errors))
        assert isinstance(errors[0], OSError)
        assert closed == [True]
    finally:
        worker.shutdown()


def test_file_menu_omits_redundant_input_selection() -> None:
    QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        file_menu = window.menuBar().actions()[0].menu()
        assert file_menu is not None
        labels = [action.text().replace("&", "") for action in file_menu.actions()]
        assert "Open Project..." in labels
        assert "Export Last Result..." in labels
        assert "Exit" in labels
        assert "Select Inputs..." not in labels
        assert not hasattr(window.menu_actions, "inputs")
    finally:
        window.close()


def test_load_tab_click_is_distinct_from_programmatic_navigation(monkeypatch) -> None:
    QApplication.instance() or QApplication([])
    window = MainWindow()
    calls = []
    monkeypatch.setattr(window.project_actions, "select_inputs", lambda: calls.append(True))
    try:
        window.show()
        window.tabs.setCurrentWidget(window.load)
        QTest.qWait(10)
        assert not calls
        QTest.mouseClick(
            window.tabs.tabBar(), Qt.MouseButton.LeftButton,
            pos=window.tabs.tabBar().tabRect(window.tabs.indexOf(window.load)).center(),
        )
        wait_until(lambda: bool(calls))
    finally:
        window.close()


@pytest.mark.parametrize("bound", [False, True])
@pytest.mark.parametrize("other_folder", [False, True])
def test_return_to_load_preserves_selected_inputs_without_dialog(
    tmp_path: Path, monkeypatch, bound: bool, other_folder: bool,
) -> None:
    from types import SimpleNamespace

    QApplication.instance() or QApplication([])
    window = MainWindow()
    dialogs = []
    inspections = []
    window.system_actions.suspend_auto_inspect = True
    source = tmp_path / "input.gro"
    source.write_text("data", encoding="ascii")
    def create_dialog(candidates, parent):
        dialog = NewProjectDialog(candidates, parent)
        dialogs.append(dialog)
        QTimer.singleShot(0, dialog.reject)
        return dialog
    monkeypatch.setattr(window.project_actions, "dialog_factory", create_dialog)
    monkeypatch.setattr(window.project_actions, "inspect_system", lambda: inspections.append(True))
    try:
        window.editor.set_root(tmp_path)
        window.load.inputs.topology.set_path(str(source))
        window.load.inputs.trajectory.set_path(str(source))
        if bound:
            window.session.project = SimpleNamespace(root=tmp_path)
        current = window.session.project
        if other_folder:
            folder = tmp_path / "other"
            folder.mkdir()
            window.editor.set_root(folder)
        window.results.show_message("retained")
        before = window.results.text.toPlainText()
        window.show()
        for _ in range(2):
            window.tabs.setCurrentWidget(window.editor)
            QTest.mouseClick(
                window.tabs.tabBar(), Qt.MouseButton.LeftButton,
                pos=window.tabs.tabBar().tabRect(window.tabs.indexOf(window.load)).center(),
            )
            QTest.qWait(20)
            assert window.tabs.currentWidget() is window.load
        assert not dialogs
        assert not inspections
        assert window.session.project is current
        assert window.results.text.toPlainText() == before
        assert Path(window.load.inputs.topology.edit.text()) == source
        assert Path(window.load.inputs.trajectory.edit.text()) == source
    finally:
        window.session.project = None
        window.close()


def test_load_without_folder_preserves_manual_file_selection(tmp_path: Path, monkeypatch) -> None:
    QApplication.instance() or QApplication([])
    window = MainWindow()
    calls = []
    source = tmp_path / "manual.gro"
    monkeypatch.setattr(window.project_actions, "dialog_factory", lambda *_: calls.append(True))
    monkeypatch.setattr("mdhelper.gui.components.paths.QFileDialog.getOpenFileName",
                        lambda *_: (str(source), ""))
    window.system_actions.suspend_auto_inspect = True
    try:
        window.show()
        QTest.mouseClick(
            window.tabs.tabBar(), Qt.MouseButton.LeftButton,
            pos=window.tabs.tabBar().tabRect(window.tabs.indexOf(window.load)).center(),
        )
        QTest.qWait(10)
        assert window.tabs.currentWidget() is window.load
        window.load.inputs.topology.button.click()
        window.load.inputs.trajectory.button.click()
        assert Path(window.load.inputs.topology.edit.text()) == source
        assert Path(window.load.inputs.trajectory.edit.text()) == source
        assert window.editor.root is None
        assert window.session.project is None
        assert not calls
    finally:
        window.close()


def test_empty_folder_load_cancel_preserves_page_and_inputs(tmp_path: Path, monkeypatch) -> None:
    QApplication.instance() or QApplication([])
    window = MainWindow()
    errors, dialogs = [], []
    monkeypatch.setattr(window.project_actions, "show_error", errors.append)
    monkeypatch.setattr("mdhelper.gui.actions.project.QFileDialog.getExistingDirectory",
                        lambda *_: str(tmp_path))
    def create_dialog(candidates, parent):
        dialog = NewProjectDialog(candidates, parent)
        dialogs.append(dialog)
        QTimer.singleShot(0, dialog.reject)
        return dialog
    window.project_actions.dialog_factory = create_dialog
    try:
        window.project_actions.open()
        assert window.editor.root == tmp_path
        assert window.tabs.currentWidget() is window.editor
        window.tabs.setCurrentWidget(window.load)
        for _ in range(2):
            window.project_actions.select_inputs()
            assert window.tabs.currentWidget() is window.load
            assert window.session.project is None
            assert not list(tmp_path.iterdir())
        assert len(dialogs) == 2
        assert not errors
    finally:
        window.close()


def test_load_selection_failure_keeps_current_binding(tmp_path: Path, monkeypatch) -> None:
    QApplication.instance() or QApplication([])
    window = MainWindow()
    errors = []
    monkeypatch.setattr(window.project_actions, "show_error", errors.append)
    def fail(*_args, **_kwargs):
        raise OSError("Unreadable directory")
    monkeypatch.setattr(window.application.projects, "discover_inputs", fail)
    window.system_actions.suspend_auto_inspect = True
    try:
        window.editor.set_root(tmp_path)
        window.load.inputs.topology.set_path(str(tmp_path / "manual.gro"))
        before = window.load.inputs.topology.edit.text()
        window.tabs.setCurrentWidget(window.load)
        window.project_actions.select_inputs()
        assert errors
        assert window.tabs.currentWidget() is window.load
        assert window.load.inputs.topology.edit.text() == before
        assert window.session.project is None
    finally:
        window.close()


def test_running_analysis_allows_browsing_but_not_input_replacement(
    tmp_path: Path, monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    window = MainWindow()
    notices, dialogs = [], []
    monkeypatch.setattr(window.project_actions, "analysis_running", lambda: True)
    monkeypatch.setattr(QMessageBox, "information", lambda *_: notices.append(True))
    monkeypatch.setattr(window.project_actions, "dialog_factory", lambda *_: dialogs.append(True))
    monkeypatch.setattr("mdhelper.gui.actions.project.QFileDialog.getExistingDirectory",
                        lambda *_: str(tmp_path))
    window.system_actions.suspend_auto_inspect = True
    try:
        window.load.inputs.topology.set_path(str(tmp_path / "manual.gro"))
        before = window.load.inputs.topology.edit.text()
        window.analysis_actions.controller.running_changed.emit(True)
        assert not window.load.inputs.isEnabled()
        window.project_actions.open()
        assert window.editor.root == tmp_path
        assert window.editor.isEnabled()
        assert not notices
        window.tabs.setCurrentWidget(window.load)
        window.project_actions.select_inputs()
        assert notices and not dialogs
        assert window.tabs.currentWidget() is window.load
        assert window.load.inputs.topology.edit.text() == before
        window.analysis_actions.controller.running_changed.emit(False)
        assert window.load.inputs.isEnabled()
    finally:
        window.close()


@pytest.mark.parametrize("nested", [False, True])
def test_load_click_confirms_real_dialog_and_readies_session(
    tmp_path: Path, monkeypatch, nested: bool,
) -> None:
    from tests.support.molecular import write_trajectory as _write_trajectory

    QApplication.instance() or QApplication([])
    root = tmp_path / "workspace"
    root.mkdir()
    source = (tmp_path if nested else root) / "system.gro"
    _write_trajectory(source)
    window = MainWindow()
    errors = []
    monkeypatch.setattr("mdhelper.gui.components.path_choice.QFileDialog.getOpenFileName",
                        lambda *_: (str(source), ""))
    monkeypatch.setattr(window.project_actions, "show_error", errors.append)
    monkeypatch.setattr(window.system_actions, "show_error", errors.append)
    def create_dialog(candidates, parent):
        dialog = NewProjectDialog(candidates, parent)
        def accept():
            for combo in (dialog.topology, dialog.trajectory):
                if nested:
                    combo.setCurrentIndex(combo.count() - 1)
                    combo.activated.emit(combo.count() - 1)
                else:
                    combo.setCurrentIndex(next(
                        index for index in range(combo.count()) if combo.itemData(index) == source
                    ))
            dialog.accept()
        QTimer.singleShot(0, accept)
        return dialog
    window.project_actions.dialog_factory = create_dialog
    try:
        window.editor.set_root(root)
        window.show()
        QTest.mouseClick(
            window.tabs.tabBar(), Qt.MouseButton.LeftButton,
            pos=window.tabs.tabBar().tabRect(window.tabs.indexOf(window.load)).center(),
        )
        wait_until(lambda: window.session.project is not None or bool(errors))
        assert not errors
        assert window.session.state.phase is SessionPhase.READY
        assert window.load.inputs.topology.edit.text() == str(source)
        assert window.load.inputs.trajectory.edit.text() == str(source)
        assert window.tabs.currentWidget() is window.load
        project = window.session.project
        manifest = project.manifest_path.read_bytes()
        window.results.show_message("retained result")
        def cancel_dialog(candidates, parent):
            dialog = NewProjectDialog(candidates, parent)
            def cancel():
                assert dialog.topology_path == source
                assert dialog.trajectory_path == source
                assert dialog.index_path is None
                dialog.reject()
            QTimer.singleShot(0, cancel)
            return dialog
        window.project_actions.dialog_factory = cancel_dialog
        for _ in range(2):
            window.project_actions.select_inputs()
            assert window.session.project is project
            assert project.manifest_path.read_bytes() == manifest
            assert window.results.text.toPlainText() == "retained result"
            assert window.tabs.currentWidget() is window.load
    finally:
        window.close()


def test_input_dialog_browse_and_cancel(tmp_path: Path, monkeypatch) -> None:
    from mdhelper.app import InputCandidates

    QApplication.instance() or QApplication([])
    dialog = NewProjectDialog(InputCandidates(tmp_path, (), (), ()))
    picked = tmp_path / "nested" / "selected.gro"
    paths = iter([str(picked), "", str(picked), str(picked), str(picked)])
    monkeypatch.setattr("mdhelper.gui.components.path_choice.QFileDialog.getOpenFileName",
                        lambda *_: (next(paths), ""))
    try:
        accept = dialog.buttons.button(QDialogButtonBox.StandardButton.Ok)
        assert not accept.isEnabled()
        assert set(dialog.findChildren(QPushButton)) == set(dialog.buttons.buttons())
        def browse(combo):
            combo.setCurrentIndex(combo.count() - 1)
            combo.activated.emit(combo.count() - 1)
        browse(dialog.topology)
        assert dialog.topology_path == picked
        count = dialog.topology.count()
        browse(dialog.topology)
        assert dialog.topology_path == picked
        browse(dialog.topology)
        assert dialog.topology.count() == count
        assert not accept.isEnabled()
        browse(dialog.trajectory)
        browse(dialog.index_file)
        assert accept.isEnabled()
        assert dialog.trajectory_path == dialog.index_path == picked
        dialog.set_inputs({"topology": picked, "trajectory": picked})
        assert dialog.index_path is None
    finally:
        dialog.close()


def test_input_dialog_prefills_external_paths_and_cancel_preserves_binding(tmp_path: Path) -> None:
    from mdhelper.app import InputCandidates
    from mdhelper.gui.dialogs.projects import NewProjectDialog

    QApplication.instance() or QApplication([])
    inputs = {name: tmp_path / name for name in ("topology", "trajectory", "index")}
    dialog = NewProjectDialog(InputCandidates(tmp_path, (), (), ()))
    dialog.set_inputs(inputs)
    assert dialog.topology_path == inputs["topology"]
    assert dialog.trajectory_path == inputs["trajectory"]
    assert dialog.index_path == inputs["index"]
    dialog.reject()
    assert dialog.result() == QDialog.DialogCode.Rejected
    dialog.close()
