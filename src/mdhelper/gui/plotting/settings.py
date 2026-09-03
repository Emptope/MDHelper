"""Advanced plot appearance settings."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mdhelper.core.plotting import (
    MAX_PLOT_FONT_SIZE,
    MAX_PLOT_LINE_WIDTH,
    MIN_PLOT_FONT_SIZE,
    MIN_PLOT_LINE_WIDTH,
    PLOT_LEGEND_LOCATIONS,
    PlotAppearance,
)


class PlotSettingsDialog(QDialog):
    """Edit plot appearance without mutating the active plot until applied."""

    applied = Signal(object)
    reverted = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Advanced Plot Settings")
        self.setMinimumWidth(440)
        self._initial = PlotAppearance()
        self._applied = self._initial

        self.line_width = _number_control(
            MIN_PLOT_LINE_WIDTH,
            MAX_PLOT_LINE_WIDTH,
            0.1,
        )
        self.grid_visible = QCheckBox("Show grid")
        self.legend_visible = QCheckBox("Show legend")
        self.legend_location = QComboBox()
        for location in PLOT_LEGEND_LOCATIONS:
            self.legend_location.addItem(location.label, location.key)
        self.legend_visible.toggled.connect(self.legend_location.setEnabled)

        display_form = QFormLayout()
        display_form.setHorizontalSpacing(12)
        display_form.setVerticalSpacing(10)
        display_form.addRow("Line width", self.line_width)
        display_form.addRow("", self.grid_visible)
        display_form.addRow("", self.legend_visible)
        display_form.addRow("Legend position", self.legend_location)
        display = QGroupBox("Display")
        display.setLayout(display_form)

        self.title_font_size = _font_control()
        self.label_font_size = _font_control()
        self.tick_font_size = _font_control()
        self.legend_font_size = _font_control()
        text_form = QFormLayout()
        text_form.setHorizontalSpacing(12)
        text_form.setVerticalSpacing(10)
        text_form.addRow("Title", self.title_font_size)
        text_form.addRow("Axis labels", self.label_font_size)
        text_form.addRow("Tick labels", self.tick_font_size)
        text_form.addRow("Legend", self.legend_font_size)
        text = QGroupBox("Font Size")
        text.setLayout(text_form)

        self.reset_button = QPushButton("Reset")
        self.apply_button = QPushButton("Apply")
        self.ok_button = QPushButton("OK")
        self.cancel_button = QPushButton("Cancel")
        self.ok_button.setDefault(True)
        self.reset_button.clicked.connect(
            lambda: self.set_appearance(PlotAppearance())
        )
        self.apply_button.clicked.connect(self._apply)
        self.ok_button.clicked.connect(self._accept)
        self.cancel_button.clicked.connect(self.reject)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)
        actions.addWidget(self.reset_button)
        actions.addStretch(1)
        actions.addWidget(self.ok_button)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.apply_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(display)
        layout.addWidget(text)
        layout.addLayout(actions)
        self.set_appearance(self._initial)

    def begin(self, appearance: PlotAppearance) -> None:
        if self.isVisible():
            return
        appearance.validate()
        self._initial = appearance
        self._applied = appearance
        self.set_appearance(appearance)

    def _apply(self) -> None:
        self._applied = self.appearance()
        self.applied.emit(self._applied)

    def _accept(self) -> None:
        self._apply()
        self.accept()

    def reject(self) -> None:
        if self._applied != self._initial:
            self._applied = self._initial
            self.reverted.emit(self._initial)
        super().reject()

    def appearance(self) -> PlotAppearance:
        appearance = PlotAppearance(
            legend_visible=self.legend_visible.isChecked(),
            legend_location=str(self.legend_location.currentData()),
            grid_visible=self.grid_visible.isChecked(),
            line_width=self.line_width.value(),
            title_font_size=self.title_font_size.value(),
            label_font_size=self.label_font_size.value(),
            tick_font_size=self.tick_font_size.value(),
            legend_font_size=self.legend_font_size.value(),
        )
        appearance.validate()
        return appearance

    def set_appearance(self, appearance: PlotAppearance) -> None:
        appearance.validate()
        self.legend_visible.setChecked(appearance.legend_visible)
        index = self.legend_location.findData(appearance.legend_location)
        self.legend_location.setCurrentIndex(index)
        self.legend_location.setEnabled(appearance.legend_visible)
        self.grid_visible.setChecked(appearance.grid_visible)
        self.line_width.setValue(appearance.line_width)
        self.title_font_size.setValue(appearance.title_font_size)
        self.label_font_size.setValue(appearance.label_font_size)
        self.tick_font_size.setValue(appearance.tick_font_size)
        self.legend_font_size.setValue(appearance.legend_font_size)


def _number_control(
    minimum: float,
    maximum: float,
    step: float,
) -> QDoubleSpinBox:
    control = QDoubleSpinBox()
    control.setRange(minimum, maximum)
    control.setSingleStep(step)
    control.setDecimals(1)
    return control


def _font_control() -> QDoubleSpinBox:
    return _number_control(MIN_PLOT_FONT_SIZE, MAX_PLOT_FONT_SIZE, 1.0)
