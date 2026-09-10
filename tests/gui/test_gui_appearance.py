"""Theme lifecycle and painted-pixel regressions, also runnable with Cocoa."""

from __future__ import annotations

import os
import warnings
from collections.abc import Iterator
from dataclasses import replace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6", reason="GUI dependencies are not installed")

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QStyleFactory,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

import mdhelper.gui.theme as theme
from mdhelper.app import ApplicationService
from mdhelper.gui.dialogs.integrations import IntegrationsDialog
from mdhelper.services.config import ThemeMode, UserConfig


@pytest.fixture
def appearance() -> Iterator[theme.ThemeController]:
    app = QApplication.instance() or QApplication([])
    controller = theme.theme_controller(app)
    state = replace(controller.state, palette=QPalette(controller.state.palette))
    palette, font, sheet = QPalette(app.palette()), QFont(app.font()), app.styleSheet()
    style = app.style().objectName() or controller._active_style
    app.installEventFilter(controller)
    try:
        yield controller
    finally:
        controller.state.changing = True
        controller._refresh_timer.stop()
        if hasattr(app.styleHints(), "setColorScheme") and theme._IS_MACOS:
            app.styleHints().setColorScheme({
                "system": Qt.ColorScheme.Unknown,
                "dark": Qt.ColorScheme.Dark,
                "light": Qt.ColorScheme.Light,
            }[state.mode])
        app.setStyleSheet("")
        app.setStyle(style)
        app.setPalette(palette)
        app.setStyleSheet(sheet)
        app.setFont(font)
        app.processEvents()
        controller.state = state
        controller._active_style = style


def settle(app: QApplication) -> None:
    for _ in range(3):
        app.processEvents()


def test_mac_content_titles_follow_application_font(
    appearance: theme.ThemeController, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(theme, "_IS_MACOS", True)
    app = appearance.application
    panel = QWidget()
    layout = QVBoxLayout(panel)
    group = QGroupBox("Inputs")
    form = QVBoxLayout(group)
    label = QLabel("Topology")
    form.addWidget(label)
    table = QTableWidget(1, 2)
    table.setHorizontalHeaderLabels(("Species", "Numbers"))
    layout.addWidget(group)
    layout.addWidget(table)
    panel.resize(700, 450)
    panel.show()
    try:
        for size in (11, 18, 11):
            font = QFont(app.font())
            font.setPointSize(size)
            app.setFont(font)
            for mode in ("system", "light", "dark"):
                appearance.apply(mode)
                settle(app)
                for widget in (group, label, table, table.horizontalHeader()):
                    assert widget.font().pointSizeF() == size
                assert label.height() >= label.fontMetrics().height()
                header = table.horizontalHeader()
                assert header.height() >= header.fontMetrics().height()
                assert f"QGroupBox::title {{ font-size: {size}pt; }}" in app.styleSheet()
    finally:
        panel.close()
        panel.deleteLater()


def painted_background(widget: QWidget) -> QColor:
    image = widget.grab().toImage()
    ratio = image.devicePixelRatio()
    # Far from text, borders, scrollbars, and native step/dropdown arrows.
    return image.pixelColor(int((widget.width() - 40) * ratio), int(widget.height() / 2 * ratio))


def assert_color(actual: QColor, expected: str) -> None:
    # Cocoa's color-space conversion can shift rendered RGB by a few levels.
    assert max(abs(a - b) for a, b in zip(
        actual.getRgb()[:3], QColor(expected).getRgb()[:3], strict=True,
    )) <= 5, (actual.name(), expected)
    assert actual.alpha() == 255


@pytest.mark.parametrize("mode", ["system", "light", "dark"])
@pytest.mark.parametrize("point_size", [11, 28])
def test_mac_themes_paint_surfaces_without_clipping(
    appearance: theme.ThemeController, monkeypatch: pytest.MonkeyPatch,
    mode: ThemeMode, point_size: int,
) -> None:
    monkeypatch.setattr(theme, "_IS_MACOS", True)
    app = appearance.application
    appearance.apply(mode)
    font = QFont(app.font())
    font.setPointSize(point_size)
    app.setFont(font)
    panel = QWidget()
    layout = QVBoxLayout(panel)
    line = QLineEdit("Editable")
    readonly = QPlainTextEdit("Read-only")
    readonly.setReadOnly(True)
    table = QTableWidget(0, 2)
    number = QDoubleSpinBox()
    combo = QComboBox()
    combo.setEditable(True)
    combo.addItem("Editable choice")
    button = QPushButton("Native button")
    for widget in (line, readonly, table, number, combo, button):
        layout.addWidget(widget)
    panel.resize(700, 700)
    panel.show()
    try:
        settle(app)
        dark = app.palette().color(QPalette.ColorRole.Window).lightness() < 128
        colors = theme._MAC_DARK if dark else theme._MAC_LIGHT
        assert_color(painted_background(line), colors.input)
        assert_color(painted_background(readonly), colors.readonly)
        assert_color(painted_background(table.viewport()), colors.input)
        for widget in (line, number, combo, button):
            assert widget.height() >= widget.sizeHint().height()
        for child in (number.findChild(QLineEdit), combo.lineEdit()):
            # Native embedded editors need room for glyphs, not the font's
            # entire line box (which includes unused ascent/descent space).
            # Include ascenders and descenders even in a numeric editor.
            glyphs = child.fontMetrics().tightBoundingRect("Ag" + child.text())
            assert child.height() >= glyphs.height()
        assert appearance._active_style == appearance.state.style
        assert app.font().pointSize() == point_size
    finally:
        panel.close()
        panel.deleteLater()


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_mac_input_state_changes_repaint(
    appearance: theme.ThemeController, monkeypatch: pytest.MonkeyPatch, mode: ThemeMode,
) -> None:
    monkeypatch.setattr(theme, "_IS_MACOS", True)
    appearance.apply(mode)
    app = appearance.application
    colors = theme._MAC_DARK if mode == "dark" else theme._MAC_LIGHT
    panel = QWidget()
    layout = QVBoxLayout(panel)
    edit = QLineEdit("Selected text")
    text = QPlainTextEdit("Read-only can change after showing")
    other = QPushButton("Other focus")
    for widget in (edit, text, other):
        layout.addWidget(widget)
    panel.resize(550, 350)
    panel.show()
    panel.activateWindow()
    try:
        settle(app)
        for widget in (edit, text):
            widget.setReadOnly(True)
            settle(app)
            assert_color(painted_background(widget), colors.readonly)
            widget.setReadOnly(False)
            settle(app)
            assert_color(painted_background(widget), colors.input)
            widget.setEnabled(False)
            settle(app)
            assert_color(painted_background(widget), colors.disabled_input)
            assert widget.palette().color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text) \
                != widget.palette().color(QPalette.ColorGroup.Active, QPalette.ColorRole.Text)
            widget.setEnabled(True)
        settle(app)
        # Set Qt's logical activation directly: Cocoa can launch the test process
        # in the background, independently of the focus state we want to paint.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            app.setActiveWindow(panel)
        edit.setFocus()
        assert edit.hasFocus()
        image = edit.grab().toImage()
        ratio = image.devicePixelRatio()
        # A two-logical-pixel border must remain two pixels at 1x and four at 2x.
        x = image.width() // 2
        for y in range(round(2 * ratio)):
            assert_color(image.pixelColor(x, y), colors.focus)
        assert_color(image.pixelColor(x, round(3 * ratio)), colors.input)
        edit.selectAll()
        image = edit.grab().toImage()
        highlight = edit.palette().color(QPalette.ColorRole.Highlight)
        # Font metrics differ between native Cocoa and test application fonts;
        # count painted selection pixels instead of assuming a fixed text inset.
        assert sum(
            image.pixelColor(x, y) == highlight
            for x in range(image.width()) for y in range(image.height())
        ) >= 20
        edit.clear()
        edit.setPlaceholderText("Placeholder")
        assert edit.palette().color(QPalette.ColorRole.PlaceholderText) \
            != edit.palette().color(QPalette.ColorRole.Base)
    finally:
        panel.close()
        panel.deleteLater()


@pytest.mark.parametrize("macos", [False, True])
def test_repeated_switches_update_existing_and_new_widgets_without_resetting_fonts(
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
        for _ in range(3):
            for mode in ("dark", "light", "system"):
                appearance.apply(mode)
                settle(app)
                later = QLineEdit("Later dialog")
                later.show()
                settle(app)
                try:
                    assert painted_background(existing) == painted_background(later)
                    assert existing.font().pointSize() == later.font().pointSize() == 18
                    assert app.font().pointSize() == 18
                    assert not appearance.state.changing
                    assert not appearance._refresh_timer.isActive()
                    if macos:
                        # No accumulating style-sheet copies or QStyle recreation.
                        assert app.styleSheet().count("Leave composite frames") == 1
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


@pytest.mark.parametrize("style", [name for name in QStyleFactory.keys() if name != "macOS"])
def test_non_mac_styles_keep_original_palettes_and_no_mac_stylesheet(
    appearance: theme.ThemeController, monkeypatch: pytest.MonkeyPatch, style: str,
) -> None:
    monkeypatch.setattr(theme, "_IS_MACOS", False)
    app = appearance.application
    appearance.state.changing = True
    app.setStyleSheet("")
    app.setStyle(style)
    app.setPalette(app.style().standardPalette())
    appearance.state.palette = QPalette(app.palette())
    appearance.state.style = style
    appearance.state.style_sheet = ""
    appearance.state.changing = False
    for mode in ("light", "dark", "system"):
        appearance.apply(mode)
        expected = appearance.state.palette if mode == "system" else theme._palette(
            mode, appearance.state.palette,
        )
        assert app.palette() == expected
        assert app.styleSheet() == ""
        assert app.style().objectName().lower() == (style.lower() if mode == "system" else "fusion")


def test_mac_dialog_minimum_tracks_font_without_squeezing_path_fields(
    appearance: theme.ThemeController, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(theme, "_IS_MACOS", True)
    appearance.apply("dark")
    app = appearance.application
    dialog = IntegrationsDialog(ApplicationService(UserConfig()))
    dialog.show()
    try:
        minima = []
        for point_size in (11, 18, 11):
            font = QFont(app.font())
            font.setPointSize(point_size)
            app.setFont(font)
            settle(app)
            dialog.resize(dialog.minimumSize())
            settle(app)
            for row in (dialog.executable, dialog.config_file):
                assert row.edit.height() >= row.edit.sizeHint().height()
                assert row.button.height() >= row.button.sizeHint().height()
            assert dialog.height() >= dialog.minimumSizeHint().height()
            minima.append(dialog.minimumSize())
        assert minima[1].height() > minima[0].height()
        # Cocoa can settle on a slightly smaller metric after repolishing.
        # The large-font minimum must not become a permanent window constraint.
        assert minima[2].height() <= minima[0].height()
        assert minima[2].width() == minima[0].width()
    finally:
        dialog.close()
        dialog.deleteLater()


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
    # Offscreen Qt has no native color scheme. Simulate the same signal order
    # on every platform, without changing the machine's actual preference.
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
