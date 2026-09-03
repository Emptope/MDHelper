"""Composite analysis panel for the desktop GUI."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QProgressBar,
    QPushButton,
    QWidget,
)

from mdhelper.core.analysis import AnalysisRequest
from mdhelper.gui.components.layout import ActionBar, configure_button, page_layout
from mdhelper.gui.components.parameters import ParameterPanel


class AnalysisPanel(QWidget):
    run_requested = Signal()
    cancel_requested = Signal()
    details_requested = Signal()
    selection_hint_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.parameters = ParameterPanel()
        self.parameters.selection_hint_requested.connect(
            self.selection_hint_requested.emit
        )
        layout = page_layout(self)
        layout.addWidget(self.parameters, 1)
        action_bar = ActionBar("Progress", stacked=True)
        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        self.progress.setMinimumHeight(28)
        action_bar.add_widget(self.progress, 1)
        self.details_button = QPushButton("Details")
        configure_button(self.details_button)
        self.details_button.setEnabled(False)
        self.details_button.clicked.connect(self.details_requested)
        action_bar.add_widget(self.details_button)
        self.run_button = QPushButton("Run")
        self.run_button.setMinimumWidth(90)
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
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(0)

    def set_progress(self, current: int, total: int | None) -> None:
        if total:
            self.progress.setRange(0, total)
            self.progress.setValue(current)
        else:
            self.progress.setRange(0, 0)

    def set_details_available(self, available: bool) -> None:
        self.details_button.setEnabled(available)

    def reset(self) -> None:
        self.parameters.reset()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
