"""Shared Qt application lifetime for desktop tests."""

from __future__ import annotations

import gc
import os
import sys
import traceback
from importlib.util import find_spec

import pytest

# Keep collection headless by default, while allowing native Cocoa runs.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session", autouse=True)
def qapp():
    if find_spec("PySide6") is None:
        # Pure GUI state tests remain runnable in a headless installation.
        return None
    from PySide6 import QtWidgets as widgets
    # Retain the wrapper for the entire session; never create Qt at collection time.
    return widgets.QApplication.instance() or widgets.QApplication([])


@pytest.fixture(autouse=True)
def qt_callback_errors():
    errors = []
    previous = sys.excepthook

    def capture(kind, value, tb):
        errors.append("".join(traceback.format_exception(kind, value, tb)))

    sys.excepthook = capture
    try:
        yield
    finally:
        sys.excepthook = previous
    if errors:
        pytest.fail("Unhandled Qt callback exceptions:\n" + "\n".join(errors))


@pytest.fixture(autouse=True)
def flush_widget_deletions(qapp, qt_callback_errors):
    existing = set(qapp.topLevelWidgets()) if qapp is not None else set()
    yield
    if qapp is not None:
        from PySide6.QtCore import QCoreApplication, QEvent
        from shiboken6 import isValid

        from mdhelper.gui.workspace.worker import DocumentWorker

        # close() only hides widgets. Destroy them outside Qt callbacks so cyclic
        # GC cannot later tear down old widgets inside another test's event loop.
        windows = set(qapp.topLevelWidgets()) - existing
        for window in windows:
            if isValid(window):
                for worker in window.findChildren(DocumentWorker):
                    worker.shutdown()
                window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        windows.clear()
        gc.collect()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
