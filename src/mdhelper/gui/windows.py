"""Lifecycle management for non-modal GUI windows."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar, cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QMessageBox, QWidget

WindowType = TypeVar("WindowType", bound=QDialog)


class WindowManager:
    """Own, reuse, present, and close non-modal top-level windows."""

    def __init__(self, owner: QWidget):
        self._owner = owner
        self._windows: dict[type[QDialog], list[QDialog]] = {}

    def get(self, kind: type[WindowType]) -> WindowType | None:
        windows = self._windows.get(kind, ())
        return cast(WindowType, windows[0]) if windows else None

    def items(self, kind: type[WindowType]) -> tuple[WindowType, ...]:
        return tuple(cast(WindowType, window) for window in self._windows.get(kind, ()))

    def show(
        self,
        kind: type[WindowType],
        prepare: Callable[[WindowType], None] | None = None,
        *,
        setup: Callable[[WindowType], None] | None = None,
    ) -> WindowType:
        window = self.get(kind)
        if window is None:
            window = self._create(kind)
            if setup is not None:
                setup(window)
        if prepare is not None:
            prepare(window)
        self.present(window)
        return window

    def show_all(
        self,
        kind: type[WindowType],
        activate: bool = True,
    ) -> None:
        for window in self.items(kind):
            self.present(window, activate)

    def resize(
        self,
        kind: type[WindowType],
        count: int,
    ) -> tuple[WindowType, ...]:
        if count < 0:
            raise ValueError("Window count cannot be negative.")
        windows = self._windows.setdefault(kind, [])
        while len(windows) < count:
            windows.append(self._create_window(kind))
        while len(windows) > count:
            window = windows.pop()
            window.close()
            window.deleteLater()
        if not windows:
            self._windows.pop(kind, None)
        return tuple(cast(WindowType, window) for window in windows)

    def close(self, kind: type[QDialog]) -> None:
        for window in tuple(self._windows.get(kind, ())):
            window.close()

    def close_all(self) -> None:
        windows = tuple(
            window
            for group in tuple(self._windows.values())
            for window in tuple(group)
        )
        for window in windows:
            window.close()

    @staticmethod
    def present(window: QDialog, activate: bool = True) -> None:
        window.show()
        window.raise_()
        if activate:
            window.activateWindow()

    def _create(self, kind: type[WindowType]) -> WindowType:
        window = self._create_window(kind)
        self._windows[kind] = [window]
        return window

    def _create_window(self, kind: type[WindowType]) -> WindowType:
        window = kind(self._owner)
        window.setWindowModality(Qt.WindowModality.NonModal)
        return window


def show_notice(
    parent: QWidget,
    notice: QMessageBox | None,
    title: str,
    text: str,
) -> QMessageBox:
    """Create or refresh one non-modal child notice."""

    if notice is None:
        notice = QMessageBox(parent)
        notice.setIcon(QMessageBox.Icon.Information)
        notice.setStandardButtons(QMessageBox.StandardButton.Ok)
        notice.setWindowModality(Qt.WindowModality.NonModal)
    notice.setWindowTitle(title)
    notice.setText(text)
    WindowManager.present(notice)
    return notice
