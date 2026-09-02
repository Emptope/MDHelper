"""Standalone plot window used by the result panel."""

from __future__ import annotations

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtWidgets import QDialog, QVBoxLayout

from mdhelper.core.plotting import (
    DEFAULT_PLOT_SIZE,
    PlotLimits,
    PlotModel,
    draw_plot,
)


class PlotWindow(QDialog):
    """Display the current result figure independently from result metadata."""

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowTitle("MDHelper Plot")
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
        width, height = self.canvas.get_width_height()
        margins = layout.contentsMargins()
        self.resize(
            width + margins.left() + margins.right(),
            height + margins.top() + margins.bottom(),
        )

    def draw(self, model: PlotModel, scheme: str, limits: PlotLimits) -> None:
        self.figure.clear()
        self.figure.set_facecolor("white")
        axis = self.figure.add_subplot(1, 1, 1)
        draw_plot(axis, model, scheme, limits)
        self.setWindowTitle(f"MDHelper Plot - {model.title}")
        _style_plot(self.figure)
        self.canvas.draw_idle()

    def clear_plot(self) -> None:
        self.figure.clear()
        self.figure.set_facecolor("white")
        self.setWindowTitle("MDHelper Plot")
        self.canvas.draw_idle()


def _style_plot(figure: Figure) -> None:
    """Keep plots in a consistent light publication style."""

    figure.set_facecolor("white")
    for axis in figure.axes:
        axis.set_facecolor("white")
        axis.title.set_color("#202020")
        axis.xaxis.label.set_color("#202020")
        axis.yaxis.label.set_color("#202020")
        axis.tick_params(colors="#202020")
        for spine in axis.spines.values():
            spine.set_color("#707070")
        if axis.patch.get_visible():
            axis.grid(color="#b0b0b0", alpha=0.35)
        else:
            axis.grid(False)
