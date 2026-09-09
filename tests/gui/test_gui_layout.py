"""Geometry regressions for native macOS and cross-platform Qt styles."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6", reason="GUI dependencies are not installed")

from PySide6.QtGui import QFont, QPalette
from PySide6.QtWidgets import QApplication, QPushButton, QStyleFactory, QVBoxLayout, QWidget

from mdhelper.app import ApplicationService, InputCandidates
from mdhelper.gui.components.inputs import InputPanel
from mdhelper.gui.components.layout import configure_button
from mdhelper.gui.components.parameters.energy import EnergyParameters
from mdhelper.gui.components.parameters.radial import RadialParameters
from mdhelper.gui.components.selections import SelectionInput
from mdhelper.gui.dialogs.integrations import IntegrationsDialog
from mdhelper.gui.dialogs.projects import NewProjectDialog
from mdhelper.gui.plotting.controls import PlotControls
from mdhelper.gui.plotting.settings import PlotSettingsDialog
from mdhelper.gui.theme import theme_controller
from mdhelper.gui.workflows.dialog import WorkflowDialog
from mdhelper.services.config import UserConfig


@pytest.fixture(params=QStyleFactory.keys())
def styled_app(request: pytest.FixtureRequest) -> Iterator[QApplication]:
    app = QApplication.instance() or QApplication([])
    style = app.style().objectName() or theme_controller(app)._active_style
    font = QFont(app.font())
    palette = QPalette(app.palette())
    app.setStyle(request.param)
    try:
        yield app
    finally:
        app.setStyle(style)
        app.setPalette(palette)
        app.setFont(font)


@pytest.mark.parametrize("point_size", [11, 18])
@pytest.mark.parametrize("kind", ["inputs", "radial", "energy"])
def test_form_fields_use_available_width(
    styled_app: QApplication, point_size: int, kind: str
) -> None:
    if kind == "inputs":
        panel = InputPanel()
        fields = [panel.topology, panel.trajectory, panel.index_file]
    elif kind == "radial":
        panel = RadialParameters(lambda: None)
        fields = [panel.queue, panel.r_max, panel.bin_width]
    else:
        panel = EnergyParameters()
        fields = [panel.file]
    panel.setFont(QFont(styled_app.font().family(), point_size))
    panel.resize(1100, 700)
    panel.show()
    try:
        styled_app.processEvents()
        widths = [field.width() for field in fields]
        right = panel.contentsRect().right() - panel.layout().contentsMargins().right()
        for field in fields:
            assert abs(field.geometry().right() - right) <= 4
        panel.resize(panel.width() + 240, panel.height())
        styled_app.processEvents()
        for field, width in zip(fields, widths, strict=True):
            assert field.width() == pytest.approx(width + 240, abs=4)
    finally:
        panel.close()


@pytest.mark.parametrize("kind", ["project", "integrations", "plot", "workflow"])
def test_dialog_form_fields_use_available_width(
    styled_app: QApplication, kind: str, tmp_path: Path,
) -> None:
    if kind == "project":
        dialog = NewProjectDialog(InputCandidates(tmp_path, (), (), ()))
        fields = [dialog.topology, dialog.trajectory, dialog.index_file]
    elif kind == "integrations":
        dialog = IntegrationsDialog(ApplicationService(UserConfig()))
        fields = [dialog.executable, dialog.config_file, dialog.capabilities]
    elif kind == "plot":
        dialog = PlotSettingsDialog()
        fields = [dialog.line_width, dialog.legend_location, dialog.title_font_size]
    else:
        dialog = WorkflowDialog()
        fields = [dialog.choice]
    dialog.resize(900, 700)
    dialog.show()
    try:
        styled_app.processEvents()
        widths = [field.width() for field in fields]
        dialog.resize(dialog.width() + 240, dialog.height())
        styled_app.processEvents()
        for field, width in zip(fields, widths, strict=True):
            assert field.width() == pytest.approx(width + 240, abs=4)
    finally:
        dialog.close()


def test_compact_controls_respect_native_and_large_font_size_hints(
    styled_app: QApplication,
) -> None:
    panel = QWidget()
    layout = QVBoxLayout(panel)
    button = configure_button(QPushButton("Add Current"), compact=True)
    selection = SelectionInput()
    layout.addWidget(button)
    layout.addWidget(selection)
    panel.show()
    try:
        for point_size in (11, 28):
            panel.setFont(QFont(styled_app.font().family(), point_size))
            panel.adjustSize()
            styled_app.processEvents()
            assert button.height() >= button.sizeHint().height()
            assert selection.height() >= selection.sizeHint().height()
    finally:
        panel.close()


def test_plot_controls_give_spare_space_to_queue_and_fields(
    styled_app: QApplication,
) -> None:
    panel = PlotControls()
    panel.resize(700, 700)
    panel.show()
    try:
        styled_app.processEvents()
        queue_height = panel.queue.height()
        settings_height = panel.settings.height()
        field_width = panel.x_min.width()
        assert field_width > 76
        assert abs(field_width - panel.x_max.width()) <= 1
        panel.resize(940, 900)
        styled_app.processEvents()
        assert panel.queue.height() == queue_height + 200
        assert panel.settings.height() == settings_height
        assert panel.x_min.width() == pytest.approx(field_width + 120, abs=1)
    finally:
        panel.close()
