"""Workspace font resolution and configuration at the GUI composition root."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import mdhelper.gui.fonts as fonts
from mdhelper.gui.window import MainWindow
from mdhelper.services.config import GuiConfig, UserConfig, load_config, save_config


@pytest.mark.parametrize("platform,family,installed,expected", [
    ("win32", "", ["Consolas"], "Consolas"),
    ("win32", "missing", ["Consolas"], "Consolas"),
    ("win32", "custom mono", ["Consolas", "Custom Mono"], "Custom Mono"),
    ("win32", "", [], "System Mono"),
    ("win32", "missing", [], "System Mono"),
    ("darwin", "", ["Consolas"], "System Mono"),
    ("linux", "missing", ["Consolas"], "System Mono"),
    ("linux", "Custom Mono", ["Custom Mono"], "Custom Mono"),
])
def test_workspace_font_fallback(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch,
    platform: str, family: str, installed: list[str], expected: str,
) -> None:
    original = QFont(qapp.font())
    monkeypatch.setattr(fonts, "sys", SimpleNamespace(platform=platform))
    monkeypatch.setattr(fonts, "QFontDatabase", SimpleNamespace(
        SystemFont=QFontDatabase.SystemFont,
        systemFont=lambda _role: QFont("System Mono"),
        families=lambda: installed,
    ))
    result = fonts.workspace_font(family, 17.5)
    assert result.family() == expected
    assert result.pointSizeF() == 17.5
    assert qapp.font() == original


@pytest.mark.usefixtures("immediate_integration_detection")
def test_window_loads_workspace_font_and_retains_it_when_saving_theme(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    original = QFont(qapp.font())
    path = tmp_path / "config.toml"
    family = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family()
    save_config(UserConfig(gui=GuiConfig(
        font_size=12.5, workspace_font_family=family, workspace_font_size=21.5,
    )), path)
    monkeypatch.setenv("MDHELPER_CONFIG", str(path))
    window = MainWindow()
    old_mode = window.theme.mode
    try:
        editor = window.editor.editor
        for mode in ("dark", "light", "system"):
            window.menu_actions.themes[mode].trigger()
            QTest.qWait(20)
            assert editor.font().family() == family
            assert editor.font().pointSizeF() == 21.5
            assert editor.line_numbers.font() == editor.font()
            assert window.editor.cursor_position.font().pointSizeF() == 12.5
            assert window.menuBar().font().pointSizeF() == 12.5
            assert qapp.font().pointSizeF() == 12.5
            loaded = load_config(path)
            assert loaded.gui.workspace_font_family == family
            assert loaded.gui.workspace_font_size == 21.5
        # Editing the file is intentionally not a live preference change.
        loaded.gui.workspace_font_size = 16.0
        save_config(loaded, path)
        QTest.qWait(20)
        assert editor.font().pointSizeF() == 21.5
    finally:
        window.close()
        window.deleteLater()
        qapp.setFont(original)
        window.theme.apply(old_mode)
    restarted = MainWindow()
    try:
        QTest.qWait(20)
        assert restarted.editor.editor.font().pointSizeF() == 16.0
    finally:
        restarted.close()
        restarted.deleteLater()
        qapp.setFont(original)
