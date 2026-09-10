"""Regression checks for deterministic Qt test teardown."""

from __future__ import annotations

import sys

import pytest

pytest.importorskip("PySide6", reason="GUI dependencies are not installed")

from PySide6.QtWidgets import QApplication, QPushButton, QWidget
from shiboken6 import isValid

from mdhelper.gui.workspace.editor import WorkspaceEditor
from tests.gui.conftest import flush_widget_deletions, qt_callback_errors


def test_widget_teardown_deletes_closed_widgets_and_their_children(qapp: QApplication) -> None:
    retained = QWidget()
    cleanup = flush_widget_deletions.__wrapped__(qapp, None)
    next(cleanup)
    window = QWidget()
    child = QWidget(window)
    window.cycle = window
    window.close()
    try:
        with pytest.raises(StopIteration):
            next(cleanup)
        assert not isValid(window)
        assert not isValid(child)
        assert isValid(retained)
    finally:
        retained.deleteLater()
        if isValid(window):
            window.deleteLater()


def test_widget_teardown_shuts_down_document_workers(qapp: QApplication) -> None:
    cleanup = flush_widget_deletions.__wrapped__(qapp, None)
    next(cleanup)
    editor = WorkspaceEditor()
    worker = editor.worker
    try:
        with pytest.raises(StopIteration):
            next(cleanup)
        assert worker._closed
        assert not isValid(editor)
        assert not isValid(worker)
    finally:
        if isValid(editor):
            editor.shutdown()
            editor.deleteLater()


def test_qt_callback_exceptions_fail_teardown_and_restore_hook() -> None:
    previous = sys.excepthook
    capture = qt_callback_errors.__wrapped__()
    next(capture)
    button = QPushButton()

    def fail():
        raise RuntimeError("Qt callback regression")

    button.clicked.connect(fail)
    try:
        button.click()
        with pytest.raises(pytest.fail.Exception, match="Qt callback regression"):
            next(capture)
        assert sys.excepthook is previous
    finally:
        capture.close()
        button.deleteLater()
