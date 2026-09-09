import os
from pathlib import Path
from threading import Event

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QModelIndex
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from mdhelper.core.workspace import DATA_COLUMNS, DataPage, DataSection
from mdhelper.gui.workspace.data import DataView
from mdhelper.gui.workspace.editor import WorkspaceEditor
from tests.support.qt import fetch_all, wait_until


def test_streaming_model_fetches_only_requested_batches() -> None:
    QApplication.instance() or QApplication([])
    view = DataView()
    model = view.model
    requests = []
    model.page_requested.connect(requests.append)
    model.configure(0, streaming=True)
    assert not requests
    model.fetchMore()
    model.fetchMore()
    assert requests == [0]
    assert not model.canFetchMore()
    size = model.page_size
    rows = tuple(("data", str(row), str(row * 2)) for row in range(size))
    model.set_page(DataPage(DataSection("data", DATA_COLUMNS, size), 0, rows, False))
    assert model.rowCount() == size
    assert model.canFetchMore()
    assert not model.canFetchMore(model.index(0, 0))
    assert requests == [0]
    model.fetchMore(QModelIndex())
    assert requests == [0, size]
    model.set_page(DataPage(DataSection("data", DATA_COLUMNS, size), size, (), True))
    assert not model.canFetchMore()
    assert model.rowCount() == size
    assert model.data(model.index(size - 1, 2)) == str((size - 1) * 2)
    model.configure(0)
    assert not model.loading and not model.canFetchMore()
    view.close()


def test_large_text_scroll_loads_more_without_enabling_save(tmp_path: Path) -> None:
    QApplication.instance() or QApplication([])
    path = tmp_path / "large.txt"
    path.write_bytes(b"text\n" * 900_000)
    editor = WorkspaceEditor()
    try:
        editor.set_root(tmp_path)
        editor.resize(850, 600)
        editor.show()
        editor.open_path(str(path))
        wait_until(lambda: editor.current_path == str(path))
        model = editor.data.model
        wait_until(lambda: not model.loading)
        assert editor.content.currentWidget() is editor.data
        assert model.canFetchMore()
        assert not editor.save()
        first = model.rowCount()
        QTest.qWait(100)
        assert model.rowCount() == first
        model.fetchMore()
        wait_until(lambda: not model.loading)
        assert model.rowCount() > first
        fetch_all(model)
        assert not model.canFetchMore()
        editor.suspend()
        assert model.rowCount() == 0
    finally:
        editor.shutdown()
        editor.close()


def test_image_display_is_fitted_and_releases_pixels_on_navigation(tmp_path: Path) -> None:
    from PIL import Image

    QApplication.instance() or QApplication([])
    path = tmp_path / "image.data"
    Image.new("RGB", (1800, 900), (20, 40, 60)).save(path, format="PNG")
    editor = WorkspaceEditor()
    try:
        editor.set_root(tmp_path)
        editor.resize(850, 600)
        editor.show()
        editor.open_path(str(path))
        wait_until(lambda: not editor.image.pixels.isNull())
        assert editor.current_path == str(path)
        assert editor.content.currentWidget() is editor.image
        assert editor.info.text() == path.name
        assert not editor.save_button.isEnabled()
        assert not editor.save()
        image = editor.image.pixels
        assert image.width() <= editor.image.width()
        assert image.height() <= editor.image.height()
        assert image.width() / image.height() == pytest.approx(2, abs=0.02)
        assert image.pixelColor(0, 0).getRgb() == (20, 40, 60, 255)
        assert str(1800) in editor.status.text() and str(900) in editor.status.text()
        editor.suspend()
        assert editor.image.pixels.isNull()
        editor.resume()
        wait_until(lambda: not editor.image.pixels.isNull())
        editor.resize(950, 650)
        QTest.qWait(100)
        wait_until(lambda: not editor.image._pending)
        editor.clear()
        assert editor.image.source is None and editor.image.pixels.isNull()
    finally:
        editor.shutdown()
        editor.close()


def test_cancelled_image_decode_cannot_replace_new_file(tmp_path: Path, monkeypatch) -> None:
    from PIL import Image

    from mdhelper.services.workspace import images

    QApplication.instance() or QApplication([])
    path = tmp_path / "image.png"
    text = tmp_path / "notes.txt"
    text.write_text("notes", encoding="ascii")
    Image.new("RGB", (160, 80)).save(path)
    entered, release = Event(), Event()
    original = images.image_pixels

    def decode(*args):
        entered.set()
        release.wait(10)
        return original(*args)

    monkeypatch.setattr("mdhelper.services.workspace.document.image_pixels", decode)
    editor = WorkspaceEditor()
    try:
        editor.set_root(tmp_path)
        editor.show()
        editor.open_path(str(path))
        wait_until(entered.is_set)
        editor.open_path(str(text))
        release.set()
        wait_until(lambda: editor.current_path == str(text))
        assert editor.content.currentWidget() is editor.editor
        assert editor.image.pixels.isNull()
        assert editor.editor.toPlainText() == text.read_text(encoding="ascii")
    finally:
        release.set()
        editor.shutdown()
        editor.close()
