"""Native UI-font configuration."""

from __future__ import annotations

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication


def configure_ui_font(
    application: QApplication,
    point_size: float = 11.0,
) -> None:
    """Apply the configured size without replacing the platform UI font."""

    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
    font.setPointSizeF(point_size)
    font.setHintingPreference(QFont.HintingPreference.PreferDefaultHinting)
    font.setStyleStrategy(QFont.StyleStrategy.PreferDefault)
    application.setFont(font)
