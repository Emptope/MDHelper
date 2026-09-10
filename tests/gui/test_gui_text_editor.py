"""File text display, gutter geometry, and editor status regressions."""

from __future__ import annotations

from math import ceil
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from mdhelper.core.workspace import WorkspaceFile
from mdhelper.gui.theme import theme_controller
from mdhelper.gui.workspace.editor import WorkspaceEditor
from mdhelper.gui.workspace.text import FileTextEditor
from tests.support.qt import wait_until


def test_line_numbers_resize_scroll_and_repaint_without_changing_text() -> None:
    app = QApplication.instance() or QApplication([])
    controller = theme_controller(app)
    old_mode = controller.mode
    controller.apply("dark")
    editor = FileTextEditor()
    editor.resize(500, 300)
    editor.show()
    try:
        assert editor.font().pointSizeF() >= 14
        assert editor.blockCount() == 1
        small = editor.line_number_width()
        text = "\n".join(f"line {i}: " + "long text " * 30 for i in range(1, 1001))
        editor.setPlainText(text)
        QTest.qWait(20)
        assert editor.line_number_width() > small
        assert editor.viewportMargins().left() == editor.line_number_width()
        assert editor.line_numbers.geometry().right() < editor.viewport().geometry().left()
        assert editor.line_numbers.height() == editor.viewport().height()
        assert not editor.document().isModified()
        editor.verticalScrollBar().setValue(450)
        QTest.qWait(20)
        assert editor.firstVisibleBlock().blockNumber() > 0
        gutter_rect = editor.line_numbers.geometry()
        before = editor.line_numbers.grab().toImage()
        editor.horizontalScrollBar().setValue(200)
        QTest.qWait(20)
        assert editor.line_numbers.geometry() == gutter_rect
        assert editor.line_numbers.grab().toImage() == before
        assert editor.toPlainText() == text
        # Two colors suffice when the platform disables font antialiasing.
        background = editor.palette().alternateBase().color()
        assert any(before.pixelColor(x, y) != background for x in range(before.width())
                   for y in range(before.height()))
        # Keep a full 16 logical pixels of blank space to the right of the numbers.
        ratio = before.devicePixelRatio()
        gap_start = before.width() - round(16 * ratio)
        background = before.pixelColor(before.width() - 1, before.height() // 2)
        assert all(
            before.pixelColor(x, y) == background
            for x in range(gap_start, before.width()) for y in range(before.height())
        )
        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        editor.setTextCursor(cursor)
        assert editor.viewport().rect().contains(editor.cursorRect())
        editor.insertPlainText("\nlast")
        assert editor.blockCount() == 1001
        editor.undo()
        assert editor.toPlainText() == text
        editor.setReadOnly(True)
        QTest.keyClicks(editor, "ignored")
        assert editor.toPlainText() == text
        editor.clear()
        assert editor.line_number_width() == small
    finally:
        editor.close()
        editor.deleteLater()
        controller.apply(old_mode)


def test_editor_font_tracks_larger_application_font() -> None:
    app = QApplication.instance() or QApplication([])
    original = QFont(app.font())
    controller = theme_controller(app)
    old_mode = controller.mode
    editor = FileTextEditor()
    try:
        for size in (11, 18, 11):
            font = QFont(original)
            font.setPointSize(size)
            app.setFont(font)
            for mode in ("system", "light", "dark"):
                controller.apply(mode)
                QTest.qWait(20)
                assert editor.font().pointSizeF() == max(14, size)
                assert editor.viewportMargins().left() == editor.line_number_width()
                assert editor.tabStopDistance() == editor.fontMetrics().horizontalAdvance(" ") * 4
    finally:
        editor.close()
        editor.deleteLater()
        app.setFont(original)
        controller.apply(old_mode)


@pytest.mark.parametrize("readonly,point_size", [(False, 11), (True, 28)])
def test_line_spacing_scales_without_changing_text_or_hit_testing(
    readonly: bool, point_size: int,
) -> None:
    app = QApplication.instance() or QApplication([])
    original = QFont(app.font())
    editor = FileTextEditor()
    editor.resize(600, 800)
    text = "first\n\n\tthird\nfourth\nlast"
    editor.setPlainText(text)
    editor.setReadOnly(readonly)
    editor.show()
    try:
        font = QFont(original)
        font.setPointSize(point_size)
        app.setFont(font)
        QTest.qWait(20)
        block = editor.document().firstBlock()
        while block.next().isValid():
            editor.setTextCursor(QTextCursor(block))
            rect = editor.cursorRect()
            height = block.layout().lineAt(0).height()
            expected = height + ceil(height * 0.35)
            assert editor.blockBoundingRect(block).height() == expected
            editor.setTextCursor(QTextCursor(block.next()))
            assert editor.cursorRect().top() - rect.top() == pytest.approx(expected, abs=1)
            QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
            assert editor.textCursor().blockNumber() == block.blockNumber()
            block = block.next()
        assert editor.toPlainText() == text
        assert not editor.document().isModified()
        assert not editor.document().isUndoAvailable()
    finally:
        editor.close()
        editor.deleteLater()
        app.setFont(original)


def test_spacing_survives_paste_undo_redo_and_theme_switches() -> None:
    app = QApplication.instance() or QApplication([])
    controller = theme_controller(app)
    original_mode = controller.mode
    editor = FileTextEditor()
    editor.show()
    text = "first\nsecond"
    editor.setPlainText(text)
    try:
        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        editor.setTextCursor(cursor)
        editor.insertPlainText("\npasted\n\nlast")
        for mode in ("light", "dark", "system"):
            controller.apply(mode)
            QTest.qWait(20)
            block = editor.document().firstBlock()
            while block.isValid():
                rect = editor.blockBoundingRect(block)
                assert rect.height() >= block.layout().lineAt(0).height() * 1.35
                block = block.next()
            assert editor.toPlainText() == text + "\npasted\n\nlast"
        editor.undo()
        assert editor.toPlainText() == text
        assert not editor.document().isModified()
        assert not editor.document().isUndoAvailable()
        editor.redo()
        assert editor.toPlainText() == text + "\npasted\n\nlast"
        editor.setPlainText("reloaded\nfile")
        assert not editor.document().isModified()
        assert not editor.document().isUndoAvailable()
    finally:
        editor.close()
        editor.deleteLater()
        controller.apply(original_mode)


@pytest.mark.parametrize("readonly", [False, True])
def test_cursor_status_tracks_unicode_tabs_selection_and_preview_mode(
    tmp_path: Path, readonly: bool,
) -> None:
    QApplication.instance() or QApplication([])
    path = tmp_path / "sample.txt"
    text = "abc\n\t\u4e2d\U00020000z\nlast"
    path.write_text(text, encoding="utf-8")
    workspace = WorkspaceEditor()
    workspace.resize(880, 650)
    workspace.set_root(tmp_path)
    workspace.show()
    workspace.open_path(str(path))
    wait_until(lambda: workspace.current_path == str(path))
    workspace.set_file(WorkspaceFile(str(path), text, not readonly, False, "Text"))
    editor = workspace.editor
    try:
        QTest.qWait(20)
        assert workspace.cursor_position.isVisible()
        assert workspace.cursor_position.text() == "Ln 1, Col 1"
        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.NextBlock)
        cursor.movePosition(QTextCursor.MoveOperation.Right, n=3)
        editor.setTextCursor(cursor)
        assert workspace.cursor_position.text() == "Ln 2, Col 7"
        cursor.movePosition(QTextCursor.MoveOperation.Start, QTextCursor.MoveMode.KeepAnchor)
        editor.setTextCursor(cursor)
        assert workspace.cursor_position.text() == "Ln 1, Col 1 | 7 selected"
        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        editor.setTextCursor(cursor)
        assert workspace.cursor_position.text() == "Ln 3, Col 5"
        QTest.keyClick(editor, Qt.Key.Key_Left)
        assert workspace.cursor_position.text() == "Ln 3, Col 4"
        # Mouse positioning reports the same logical location as the cursor.
        QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton,
                         pos=editor.cursorRect().center())
        assert workspace.cursor_position.text() == "Ln 3, Col 4"
        for preview in (workspace.data, workspace.image):
            workspace.content.setCurrentWidget(preview)
            assert workspace.cursor_position.isHidden()
        workspace.content.setCurrentWidget(editor)
        assert workspace.cursor_position.isVisible()
        workspace.resize(760, 500)
        QTest.qWait(20)
        assert workspace.status.geometry().right() < workspace.cursor_position.geometry().left()
        workspace.clear()
        assert workspace.cursor_position.isHidden()
        assert workspace.cursor_position.text() == "Ln 1, Col 1"
    finally:
        workspace.shutdown()
        workspace.close()
        workspace.deleteLater()
