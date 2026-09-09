"""Application-wide Qt appearance modes."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import cast
from weakref import WeakKeyDictionary

from PySide6.QtCore import QEvent, QObject, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QProxyStyle,
    QStyle,
    QStyleOption,
    QStyleOptionComplex,
    QWidget,
)

from mdhelper.services.config import ThemeMode

_IS_MACOS = sys.platform == "darwin"


@dataclass(frozen=True)
class _MacColors:
    window: str
    input: str
    readonly: str
    alternate: str
    disabled_input: str
    border: str
    focus: str


@dataclass
class _ThemeState:
    style: str
    palette: QPalette
    style_sheet: str
    mode: ThemeMode = "system"
    changing: bool = False


_CONTROLLERS: WeakKeyDictionary[QApplication, ThemeController] = WeakKeyDictionary()

_MAC_LIGHT = _MacColors(
    window="#f3f4f6", input="#ffffff", readonly="#eceef2", alternate="#f7f8fa",
    disabled_input="#e5e7eb", border="#afb5bf", focus="#0969da",
)
_MAC_DARK = _MacColors(
    window="#292b2f", input="#3a3d43", readonly="#32353a", alternate="#35383e",
    disabled_input="#303237", border="#6b717b", focus="#80b4ff",
)


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


def _mac_palette(mode: ThemeMode, base: QPalette) -> QPalette:
    colors = _MAC_DARK if mode == "dark" else _MAC_LIGHT
    palette = _palette(mode, base)
    _set_colors(palette, {
        QPalette.ColorRole.Window: QColor(colors.window),
        QPalette.ColorRole.Base: QColor(colors.input),
        QPalette.ColorRole.AlternateBase: QColor(colors.alternate),
        QPalette.ColorRole.PlaceholderText: QColor("#b7bbc3" if mode == "dark" else "#636b76"),
    })
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor(colors.disabled_input),
    )
    return palette


def _mac_style_sheet(mode: ThemeMode, point_size: float = 11.0) -> str:
    """Style content surfaces only; native menus, buttons and arrows remain native."""
    colors = _MAC_DARK if mode == "dark" else _MAC_LIGHT
    editors = "QLineEdit, QTextEdit, QPlainTextEdit"
    disabled_text = "#a1a6b0" if mode == "dark" else "#6b7280"
    placeholder = "#b7bbc3" if mode == "dark" else "#636b76"
    # QAbstractItemView also matches headers, causing nested frames. Be specific.
    views = "QTableView, QTreeView, QListView"
    surfaces = f"{editors}, {views}"

    def states(selectors: str, state: str) -> str:
        return ", ".join(f"{selector.strip()}{state}" for selector in selectors.split(","))

    return f"""
/* Cocoa supplies smaller class fonts and paints group titles independently. */
QLabel, QGroupBox, QHeaderView, QAbstractItemView {{ font-size: {point_size:g}pt; }}
QGroupBox::title {{ font-size: {point_size:g}pt; }}
{surfaces} {{
    background-color: palette(base);
    color: palette(text);
    placeholder-text-color: {placeholder};
    selection-background-color: palette(highlight);
    selection-color: palette(highlighted-text);
    border: 2px solid {colors.border};
    border-radius: 4px;
}}
{editors} {{ padding: 3px 5px; }}
{views} {{
    alternate-background-color: palette(alternate-base);
    gridline-color: {colors.border};
}}
{states(editors, '[readOnly="true"]')} {{ background-color: {colors.readonly}; }}
{states(surfaces, ':disabled')} {{
    background-color: {colors.disabled_input};
    color: {disabled_text};
}}
{states(surfaces, ':focus')} {{ border-color: {colors.focus}; }}
/* Leave composite frames/arrows to Cocoa. Only color the embedded editor. */
QAbstractSpinBox QLineEdit, QComboBox QLineEdit {{
    border: none;
    border-radius: 0;
    padding: 0;
    background-color: palette(base);
}}
QAbstractSpinBox QLineEdit:disabled, QComboBox QLineEdit:disabled {{
    background-color: {colors.disabled_input};
    color: {disabled_text};
}}
""".strip()


class _MacNativeStyle(QProxyStyle):
    """Keep Cocoa painting, but let combo editors accommodate larger fonts."""

    def sizeFromContents(
        self, kind: QStyle.ContentsType, option: QStyleOption,
        size: QSize, widget: QWidget | None = None,
    ) -> QSize:
        # Qt permits a null widget here; PySide's QProxyStyle stubs do not.
        result = super().sizeFromContents(kind, option, size, cast(QWidget, widget))
        if kind == QStyle.ContentsType.CT_ComboBox:
            result.setHeight(max(result.height(), option.fontMetrics.height() + 8))
        return result

    def subControlRect(
        self, control: QStyle.ComplexControl, option: QStyleOptionComplex,
        subcontrol: QStyle.SubControl, widget: QWidget | None = None,
    ) -> QRect:
        rect = super().subControlRect(control, option, subcontrol, cast(QWidget, widget))
        if (
            control == QStyle.ComplexControl.CC_ComboBox
            and subcontrol == QStyle.SubControl.SC_ComboBoxEditField
        ):
            # Cocoa otherwise caps the embedded QLineEdit at 17px, even when
            # the outer combo and its font are much taller. Leave arrows alone.
            height = min(option.rect.height() - 4, max(rect.height(), option.fontMetrics.height()))
            rect.setHeight(height)
            rect.moveTop(option.rect.top() + (option.rect.height() - height) // 2)
        return rect


class ThemeController(QObject):
    """Apply explicit themes and restore native platform appearance when requested."""

    def __init__(self, application: QApplication):
        super().__init__(application)
        self.application = application
        self.state = _ThemeState(
            application.style().objectName(),
            QPalette(application.palette()),
            application.styleSheet(),
        )
        self._active_style = self.state.style
        self._styled_font = QFont(application.font())
        self._native_style: _MacNativeStyle | None = None
        self._window_minima: WeakKeyDictionary[QWidget, QSize] = WeakKeyDictionary()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._refresh)
        application.paletteChanged.connect(self._palette_changed)
        application.fontChanged.connect(self._font_changed)
        application.styleHints().colorSchemeChanged.connect(self._system_scheme_changed)
        if _IS_MACOS:
            application.installEventFilter(self)

    @property
    def mode(self) -> ThemeMode:
        return self.state.mode

    def apply(self, mode: ThemeMode) -> None:
        if self.state.changing:
            return
        self.state.mode = mode
        if _IS_MACOS:
            # Qt 6.8+ can switch Cocoa's native controls as well as the palette.
            # Older Qt versions still receive the palette and content styling.
            hints = self.application.styleHints()
            if hasattr(hints, "setColorScheme"):
                self.state.changing = True
                try:
                    hints.setColorScheme({
                        "system": Qt.ColorScheme.Unknown,
                        "light": Qt.ColorScheme.Light,
                        "dark": Qt.ColorScheme.Dark,
                    }[mode])
                finally:
                    self.state.changing = False
        self._refresh()

    def _refresh(self) -> None:
        if self.state.changing:
            return
        self._refresh_timer.stop()
        app = self.application
        font = QFont(app.font())
        self.state.changing = True
        try:
            mode = self.state.mode
            style = self.state.style if _IS_MACOS or mode == "system" else "Fusion"
            # Recreating QStyle on every apply resets widget metrics and fonts.
            # QStyleSheetStyle has an empty objectName; remember its base style.
            current_style = app.style().objectName() or self._active_style
            if _IS_MACOS and style.lower() == "macos" and self._native_style is None:
                native = _MacNativeStyle(style)
                native.setObjectName(style)
                native.destroyed.connect(self._native_style_destroyed)
                app.setStyle(native)
                self._native_style = native
            elif current_style.lower() != style.lower():
                app.setStyle(style)
            self._active_style = style
            sheet = self.state.style_sheet
            if _IS_MACOS:
                if mode == "system":
                    scheme = app.styleHints().colorScheme()
                    dark = scheme == Qt.ColorScheme.Dark or (
                        scheme == Qt.ColorScheme.Unknown
                        and self.state.palette.color(QPalette.ColorRole.Window).lightness() < 128
                    )
                    mode = "dark" if dark else "light"
                palette = _mac_palette(mode, self.state.palette)
                sheet = "\n".join(filter(None, (sheet, _mac_style_sheet(mode, font.pointSizeF()))))
            else:
                palette = (
                    self.state.palette if mode == "system" else _palette(mode, self.state.palette)
                )
            app.setPalette(palette)
            if app.styleSheet() != sheet or (_IS_MACOS and self._styled_font != font):
                # Qt's stylesheet caches otherwise retain old fonts in child editors.
                app.setStyleSheet(sheet)
            self._styled_font = QFont(font)
        finally:
            if app.font() != font:
                app.setFont(font)
            self.state.changing = False

    def _font_changed(self, _font: QFont) -> None:
        if _IS_MACOS and not self.state.changing:
            self._refresh_timer.start(0)

    def _native_style_destroyed(self) -> None:
        self._native_style = None

    def _palette_changed(self, palette: QPalette) -> None:
        if self.state.changing:
            return
        if self.state.mode == "system":
            self.state.palette = QPalette(palette)
        if _IS_MACOS:
            self._refresh_timer.start(0)

    def _system_scheme_changed(self, _scheme: object) -> None:
        if self.state.changing:
            return
        # Qt emits colorSchemeChanged before updating the native palette. Defer
        # until that update completes, and coalesce any paletteChanged signals.
        if not _IS_MACOS and self.state.mode == "system":
            self.state.palette = self.application.style().standardPalette()
        self._refresh_timer.start(0)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if _IS_MACOS and isinstance(watched, QWidget):
            if event.type() == QEvent.Type.ReadOnlyChange:
                # Property selectors are not repolished on readOnly changes.
                watched.style().unpolish(watched)
                watched.style().polish(watched)
                watched.update()
            elif event.type() == QEvent.Type.LayoutRequest and watched.isWindow():
                # Explicit window minima override Qt's automatic layout minimum.
                # Retain that baseline, but do not squeeze larger-font contents.
                baseline = self._window_minima.setdefault(watched, watched.minimumSize())
                minimum = baseline.expandedTo(watched.minimumSizeHint())
                if watched.minimumSize() != minimum:
                    watched.setMinimumSize(minimum)
        return super().eventFilter(watched, event)


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
