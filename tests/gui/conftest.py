"""Shared Qt application lifetime for desktop tests."""

from __future__ import annotations

import os
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
def flush_widget_deletions(qapp):
    yield
    if qapp is not None:
        from PySide6.QtCore import QCoreApplication, QEvent

        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
