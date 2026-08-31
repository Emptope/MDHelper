"""Composite analysis panel for the desktop GUI."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QProgressBar,
    QPushButton,
    QWidget,
)

from mdhelper.core.analysis import AnalysisRequest
from mdhelper.gui.layout import ActionBar, page_layout
from mdhelper.gui.parameters import ParameterPanel


class AnalysisPanel(QWidget):
    run_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.parameters = ParameterPanel()
        layout = page_layout(self)
        layout.addWidget(self.parameters, 1)
        action_bar = ActionBar("Analysis progress", stacked=True)
        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        action_bar.add_widget(self.progress, 1)
        self.run_button = QPushButton("Run Analysis")
        self.run_button.setMinimumWidth(130)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setMinimumWidth(90)
        self.cancel_button.setEnabled(False)
        self.run_button.clicked.connect(self.run_requested)
        self.cancel_button.clicked.connect(self.cancel_requested)
        action_bar.add_button(self.cancel_button)
        action_bar.add_button(self.run_button, primary=True)
        layout.addWidget(action_bar)
        self.action_bar = action_bar

    def request_series(
        self,
        common: dict[str, object],
    ) -> tuple[tuple[AnalysisRequest, str], ...]:
        return self.parameters.request_series(common)

    def apply_request(self, request: AnalysisRequest) -> None:
        self.parameters.apply_request(request)

    def set_running(self, running: bool) -> None:
        self.run_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        if running:
            self.progress.setRange(0, 0)

    def set_progress(self, current: int, total: int | None) -> None:
        if total:
            self.progress.setRange(0, total)
            self.progress.setValue(current)
        else:
            self.progress.setRange(0, 0)

    def reset(self) -> None:
        self.parameters.reset()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
