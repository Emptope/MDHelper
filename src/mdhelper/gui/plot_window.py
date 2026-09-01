"""Standalone plot window used by the result panel."""

from __future__ import annotations

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtWidgets import QDialog, QVBoxLayout

from mdhelper.core.plotting import DEFAULT_PLOT_SIZE


class PlotWindow(QDialog):
    """Display the current result figure independently from result metadata."""

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowTitle("MDHelper Plot")
        self.resize(980, 720)
        self.setMinimumSize(720, 520)
        self.figure = Figure(
            figsize=(DEFAULT_PLOT_SIZE.width, DEFAULT_PLOT_SIZE.height),
            constrained_layout=True,
            facecolor="white",
        )
        self.canvas = FigureCanvasQTAgg(self.figure)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.canvas, 1)
