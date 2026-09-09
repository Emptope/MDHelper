"""Event-loop synchronization for asynchronous GUI tests."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QApplication

if TYPE_CHECKING:
    from mdhelper.gui.workspace.data import DataModel


def wait_until(condition: Callable[[], bool], timeout: float = 10) -> None:
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        QApplication.processEvents()
        # Yield the GIL so Python document workers can make progress.
        time.sleep(0.01)
    assert condition(), "Asynchronous operation did not complete before the deadline"


def fetch_all(model: DataModel) -> None:
    wait_until(lambda: not model.loading)
    while model.canFetchMore():
        model.fetchMore()
        wait_until(lambda: not model.loading)
