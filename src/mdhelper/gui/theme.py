"""Application-wide Qt appearance modes."""

from __future__ import annotations

from dataclasses import dataclass
from weakref import WeakKeyDictionary

from PySide6.QtCore import QObject
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from mdhelper.services.config import ThemeMode


@dataclass
class _ThemeState:
    style: str
    palette: QPalette
    mode: ThemeMode = "system"
    changing: bool = False


_CONTROLLERS: WeakKeyDictionary[QApplication, ThemeController] = WeakKeyDictionary()


def _set_colors(palette: QPalette, colors: dict[QPalette.ColorRole, QColor]) -> None:
    for role, color in colors.items():
        palette.setColor(QPalette.ColorGroup.All, role, color)


def _palette(mode: ThemeMode, base: QPalette | None = None) -> QPalette:
    palette = QPalette() if base is None else QPalette(base)
    if mode == "dark":
        _set_colors(
            palette,
            {
                QPalette.ColorRole.Window: QColor("#252526"),
                QPalette.ColorRole.WindowText: QColor("#f3f3f3"),
                QPalette.ColorRole.Base: QColor("#1e1e1e"),
                QPalette.ColorRole.AlternateBase: QColor("#2d2d30"),
                QPalette.ColorRole.ToolTipBase: QColor("#333337"),
                QPalette.ColorRole.ToolTipText: QColor("#f3f3f3"),
                QPalette.ColorRole.Text: QColor("#f3f3f3"),
                QPalette.ColorRole.Button: QColor("#333337"),
                QPalette.ColorRole.ButtonText: QColor("#f3f3f3"),
                QPalette.ColorRole.BrightText: QColor("#ff6b6b"),
                QPalette.ColorRole.Link: QColor("#4daafc"),
                QPalette.ColorRole.Highlight: QColor("#0e639c"),
                QPalette.ColorRole.HighlightedText: QColor("#ffffff"),
                QPalette.ColorRole.PlaceholderText: QColor("#9d9d9d"),
            },
        )
        disabled = QColor("#858585")
        disabled_highlight = QColor("#3f3f46")
    else:
        _set_colors(
            palette,
            {
                QPalette.ColorRole.Window: QColor("#f0f0f0"),
                QPalette.ColorRole.WindowText: QColor("#202020"),
                QPalette.ColorRole.Base: QColor("#ffffff"),
                QPalette.ColorRole.AlternateBase: QColor("#f6f6f6"),
                QPalette.ColorRole.ToolTipBase: QColor("#ffffff"),
                QPalette.ColorRole.ToolTipText: QColor("#202020"),
                QPalette.ColorRole.Text: QColor("#202020"),
                QPalette.ColorRole.Button: QColor("#f0f0f0"),
                QPalette.ColorRole.ButtonText: QColor("#202020"),
                QPalette.ColorRole.BrightText: QColor("#c42b1c"),
                QPalette.ColorRole.Link: QColor("#0067c0"),
                QPalette.ColorRole.Highlight: QColor("#0a64ad"),
                QPalette.ColorRole.HighlightedText: QColor("#ffffff"),
                QPalette.ColorRole.PlaceholderText: QColor("#707070"),
            },
        )
        disabled = QColor("#767676")
        disabled_highlight = QColor("#c7c7c7")
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.PlaceholderText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, disabled)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, disabled_highlight)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.HighlightedText, disabled)
    return palette


class ThemeController(QObject):
    """Apply explicit themes and restore the native appearance for system mode."""

    def __init__(self, application: QApplication):
        super().__init__(application)
        self.application = application
        self.state = _ThemeState(
            application.style().objectName(),
            QPalette(application.palette()),
        )
        application.paletteChanged.connect(self._palette_changed)
        application.styleHints().colorSchemeChanged.connect(self._system_scheme_changed)

    @property
    def mode(self) -> ThemeMode:
        return self.state.mode

    def apply(self, mode: ThemeMode) -> None:
        if mode == "system" and self.state.mode == "system":
            return
        font = QFont(self.application.font())
        self.state.mode = mode
        self.state.changing = True
        try:
            if mode == "system":
                self.application.setStyle(self.state.style)
                self.application.setPalette(self.state.palette)
            else:
                self.application.setStyle("Fusion")
                self.application.setPalette(_palette(mode, self.state.palette))
        finally:
            self.application.setFont(font)
            self.state.changing = False

    def _palette_changed(self, palette: QPalette) -> None:
        if self.state.mode == "system" and not self.state.changing:
            self.state.palette = QPalette(palette)

    def _system_scheme_changed(self, _scheme: object) -> None:
        if self.state.mode != "system" or self.state.changing:
            return
        self.state.changing = True
        try:
            palette = self.application.style().standardPalette()
            self.application.setPalette(palette)
            self.state.palette = QPalette(palette)
        finally:
            self.state.changing = False


def theme_controller(application: QApplication | None = None) -> ThemeController:
    """Return the single theme controller associated with a Qt application."""

    app = QApplication.instance() if application is None else application
    if not isinstance(app, QApplication):
        raise RuntimeError("A QApplication must exist before configuring the theme.")
    controller = _CONTROLLERS.get(app)
    if controller is None:
        controller = ThemeController(app)
        _CONTROLLERS[app] = controller
    return controller
