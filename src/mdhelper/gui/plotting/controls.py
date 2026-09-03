"""Plot-series and display controls for the result page."""

from __future__ import annotations

from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mdhelper.core.plotting import (
    DEFAULT_PLOT_SCHEME,
    MAX_PLOT_TITLE_LENGTH,
    PLOT_SCHEMES,
    PlotLimits,
)
from mdhelper.core.units import ANGSTROM_SYMBOL
from mdhelper.gui.components.layout import PAGE_SPACING

from .table import PlotTable


class PlotControls(QWidget):
    """Build and expose the controls used to configure result plots."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(PAGE_SPACING)
        series_controls = QHBoxLayout()
        series_controls.addWidget(QLabel("Plot Queue"))
        self.combine_button = QPushButton("Combine")
        self.combine_button.setEnabled(False)
        self.separate_button = QPushButton("Separate")
        self.separate_button.setEnabled(False)
        self.remove_button = QPushButton("Remove")
        self.clear_button = QPushButton("Clear All")
        series_controls.addWidget(self.combine_button)
        series_controls.addWidget(self.separate_button)
        series_controls.addStretch(1)
        series_controls.addWidget(self.remove_button)
        series_controls.addWidget(self.clear_button)
        layout.addLayout(series_controls)

        self.series = PlotTable()
        layout.addWidget(self.series)

        self.settings = QGroupBox("Plot Settings")
        settings = QGridLayout(self.settings)
        settings.setContentsMargins(12, 10, 12, 10)
        settings.setHorizontalSpacing(10)
        settings.setVerticalSpacing(8)
        settings.addWidget(QLabel("Title"), 0, 0)
        self.title = QLineEdit()
        self.title.setMaxLength(MAX_PLOT_TITLE_LENGTH)
        self.title.setEnabled(False)
        settings.addWidget(self.title, 0, 1, 1, 2)
        settings.addWidget(QLabel("Color by"), 1, 0)
        self.scheme = QComboBox()
        for scheme in PLOT_SCHEMES:
            self.scheme.addItem(scheme.label, scheme.key)
        self.scheme.setCurrentIndex(self.scheme.findData(DEFAULT_PLOT_SCHEME))
        settings.addWidget(self.scheme, 1, 1)

        self.x_min = _limit_edit("Min")
        self.x_max = _limit_edit("Max")
        self.y_min = _limit_edit("Min")
        self.y_max = _limit_edit("Max")
        self.y2_min = _limit_edit("Min")
        self.y2_max = _limit_edit("Max")
        settings.addWidget(QLabel("Range"), 2, 0)
        settings.addWidget(QLabel("Minimum"), 2, 1)
        settings.addWidget(QLabel("Maximum"), 2, 2)
        for row, (label, minimum, maximum) in enumerate(
            (
                (f"Distance X ({ANGSTROM_SYMBOL})", self.x_min, self.x_max),
                ("Primary Y", self.y_min, self.y_max),
                ("Secondary Y", self.y2_min, self.y2_max),
            ),
            start=3,
        ):
            settings.addWidget(QLabel(label), row, 0)
            settings.addWidget(minimum, row, 1)
            settings.addWidget(maximum, row, 2)
        for column in range(3):
            settings.setColumnStretch(column, 1)
        settings.setRowStretch(settings.rowCount(), 1)
        advanced_row = QHBoxLayout()
        advanced_row.addStretch(1)
        self.advanced_button = QPushButton("Advanced...")
        advanced_row.addWidget(self.advanced_button)
        settings.addLayout(advanced_row, 7, 0, 1, 3)
        layout.addWidget(self.settings)

        self.open_button = QPushButton("Open Plot Window")
        self.open_button.setEnabled(False)

    def limit_edits(self) -> tuple[QLineEdit, ...]:
        return (
            self.x_min,
            self.x_max,
            self.y_min,
            self.y_max,
            self.y2_min,
            self.y2_max,
        )

    def limits(self) -> PlotLimits:
        values = tuple(_limit_value(edit) for edit in self.limit_edits())
        return PlotLimits(*values)

    def set_limits(self, limits: PlotLimits) -> None:
        values = (
            limits.x_min,
            limits.x_max,
            limits.y_min,
            limits.y_max,
            limits.y2_min,
            limits.y2_max,
        )
        for edit, value in zip(self.limit_edits(), values, strict=True):
            edit.setText("" if value is None else f"{value:g}")


def _limit_edit(placeholder: str) -> QLineEdit:
    edit = QLineEdit()
    validator = QDoubleValidator(edit)
    validator.setNotation(QDoubleValidator.Notation.ScientificNotation)
    edit.setValidator(validator)
    edit.setPlaceholderText(placeholder)
    edit.setMaximumWidth(76)
    return edit


def _limit_value(edit: QLineEdit) -> float | None:
    text = edit.text().strip()
    return None if not text else float(text)
