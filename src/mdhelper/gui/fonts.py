"""Native UI-font configuration."""

from __future__ import annotations

import sys

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication


def workspace_font(family: str = "", point_size: float = 14.0) -> QFont:
    """Resolve an installed editor font, falling back to a platform monospace font."""

    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    installed = {name.casefold(): name for name in QFontDatabase.families()}
    candidates = [family.strip()]
    if sys.platform == "win32":
        candidates.append("Consolas")
    for candidate in candidates:
        if candidate.casefold() in installed:
            font.setFamily(installed[candidate.casefold()])
            break
    font.setPointSizeF(point_size)
    return font


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
