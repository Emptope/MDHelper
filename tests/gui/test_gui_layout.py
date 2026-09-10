"""Regression for native minimum sizes and plot-control expansion."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

pytest.importorskip("PySide6", reason="GUI dependencies are not installed")

from PySide6.QtGui import QFont, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

from mdhelper.gui.plotting.controls import PlotControls
from mdhelper.gui.theme import theme_controller

# Exercise the host's native style and one portable style, not every installed style.
_STYLES = list(dict.fromkeys([QStyleFactory.keys()[0], "Fusion"]))


@pytest.fixture(params=_STYLES)
def styled_app(request: pytest.FixtureRequest, qapp: QApplication) -> Iterator[QApplication]:
    style = qapp.style().objectName() or theme_controller(qapp)._active_style
    font, palette = QFont(qapp.font()), QPalette(qapp.palette())
    qapp.setStyle(request.param)
    try:
        yield qapp
    finally:
        qapp.setStyle(style)
        qapp.setPalette(palette)
        qapp.setFont(font)


def test_plot_controls_expand_from_realized_minimum_size(styled_app: QApplication) -> None:
    panel = PlotControls()
    # Deliberately request less than the native minimum width.
    panel.resize(1, 700)
    panel.show()
    try:
        styled_app.processEvents()
        queue_height, settings_height = panel.queue.height(), panel.settings.height()
        widths = [panel.x_min.width(), panel.x_max.width()]
        assert min(widths) > 76
        assert min(widths) / max(widths) > 0.9
        # Qt may enlarge the initial request: use the realized geometry.
        panel.resize(panel.width() + 240, panel.height() + 200)
        styled_app.processEvents()
        assert panel.queue.height() == queue_height + 200
        assert panel.settings.height() == settings_height
        growth = [field.width() - width for field, width in zip(
            (panel.x_min, panel.x_max), widths, strict=True,
        )]
        assert sum(growth) == pytest.approx(240, abs=1)
        assert min(growth) / max(growth) > 0.9
    finally:
        panel.close()
        panel.deleteLater()
