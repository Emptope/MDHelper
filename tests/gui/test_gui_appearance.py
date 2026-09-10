"""Theme lifecycle contracts, independent of platform-specific painted pixels."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace

import pytest

pytest.importorskip("PySide6", reason="GUI dependencies are not installed")

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPalette
from PySide6.QtWidgets import QApplication, QLineEdit

import mdhelper.gui.theme as theme


@pytest.fixture
def appearance(qapp: QApplication) -> Iterator[theme.ThemeController]:
    controller = theme.theme_controller(qapp)
    state = replace(controller.state, palette=QPalette(controller.state.palette))
    palette, font, sheet = QPalette(qapp.palette()), QFont(qapp.font()), qapp.styleSheet()
    style = qapp.style().objectName() or controller._active_style
    qapp.installEventFilter(controller)
    try:
        yield controller
    finally:
        controller.state.changing = True
        controller._refresh_timer.stop()
        if hasattr(qapp.styleHints(), "setColorScheme") and theme._IS_MACOS:
            qapp.styleHints().setColorScheme({
                "system": Qt.ColorScheme.Unknown,
                "dark": Qt.ColorScheme.Dark,
                "light": Qt.ColorScheme.Light,
            }[state.mode])
        qapp.setStyleSheet("")
        qapp.setStyle(style)
        qapp.setPalette(palette)
        qapp.setStyleSheet(sheet)
        qapp.setFont(font)
        qapp.processEvents()
        controller.state = state
        controller._active_style = style


def settle(app: QApplication) -> None:
    for _ in range(3):
        app.processEvents()


@pytest.mark.parametrize("macos", [False, True])
def test_theme_switches_preserve_fonts_and_update_existing_and_new_widgets(
    appearance: theme.ThemeController, monkeypatch: pytest.MonkeyPatch, macos: bool,
) -> None:
    monkeypatch.setattr(theme, "_IS_MACOS", macos)
    app = appearance.application
    font = QFont(app.font())
    font.setPointSize(18)
    app.setFont(font)
    existing = QLineEdit("Existing")
    existing.show()
    try:
        for mode in ("dark", "light", "system", "dark"):
            appearance.apply(mode)
            settle(app)
            later = QLineEdit("Later dialog")
            later.show()
            settle(app)
            try:
                assert existing.palette() == later.palette()
                assert existing.font().pointSize() == later.font().pointSize() == 18
                assert app.font().pointSize() == 18
                assert not appearance.state.changing
                assert not appearance._refresh_timer.isActive()
                if macos:
                    style = app.style()
                    appearance.apply(mode)
                    assert app.style() is style
                else:
                    assert app.styleSheet() == appearance.state.style_sheet
            finally:
                later.close()
                later.deleteLater()
    finally:
        existing.close()
        existing.deleteLater()


def test_system_scheme_signal_is_deferred_and_preserves_font(
    appearance: theme.ThemeController, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(theme, "_IS_MACOS", True)
    app = appearance.application
    appearance.apply("system")
    font = QFont(app.font())
    font.setPointSize(18)
    app.setFont(font)
    hints = app.styleHints()
    for scheme in (Qt.ColorScheme.Light, Qt.ColorScheme.Dark, Qt.ColorScheme.Light):
        monkeypatch.setattr(hints, "colorScheme", lambda value=scheme: value)
        hints.colorSchemeChanged.emit(scheme)
        assert appearance._refresh_timer.isActive()
        settle(app)
        expected = theme._MAC_DARK if scheme == Qt.ColorScheme.Dark else theme._MAC_LIGHT
        assert app.palette().color(QPalette.ColorRole.Base).name() == expected.input
        assert app.font().pointSize() == 18
        assert appearance.mode == "system"
        assert not appearance._refresh_timer.isActive()
