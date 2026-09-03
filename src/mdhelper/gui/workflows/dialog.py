"""Ordered workflow project review dialog."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from mdhelper.core.analysis import AnalysisType, analysis_label
from mdhelper.gui.components.layout import ActionBar
from mdhelper.gui.components.parameters import ParameterPanel
from mdhelper.gui.controllers.analysis_state import RunItem

PanelSetup = Callable[[ParameterPanel], None]
ItemBuilder = Callable[[ParameterPanel], tuple[RunItem, ...]]


class WorkflowDialog(QDialog):
    """Review every configured project before submitting one analysis batch."""

    run_requested = Signal(object)
    configure_requested = Signal()
    failed = Signal(object)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Run Workflow")
        self.resize(820, 660)
        self.setMinimumSize(720, 580)
        self._workflows: dict[str, tuple[AnalysisType, ...]] = {}
        self._setup: PanelSetup = lambda _panel: None
        self._build: ItemBuilder | None = None
        self.panels: tuple[ParameterPanel, ...] = ()

        self.choice = QComboBox()
        self.choice.currentIndexChanged.connect(self._workflow_changed)
        selection = QFormLayout()
        selection.addRow("Workflow", self.choice)

        self.steps = QListWidget()
        self.steps.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.steps.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.steps.setMaximumWidth(290)
        self.stack = QStackedWidget()
        self.content = QSplitter()
        self.content.setChildrenCollapsible(False)
        self.content.addWidget(self.steps)
        self.content.addWidget(self.stack)
        self.content.setStretchFactor(0, 0)
        self.content.setStretchFactor(1, 1)

        self.empty = QLabel("No workflows are configured.")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.configure_button = self._button("Open Configuration")
        self.configure_button.clicked.connect(self.configure_requested)
        self.back_button = self._button("Back")
        self.next_button = self._button("Next")
        self.run_button = self._button("Run")
        close_button = self._button("Close")
        self.back_button.clicked.connect(self._back)
        self.next_button.clicked.connect(self._next)
        self.run_button.clicked.connect(self._run)
        close_button.clicked.connect(self.reject)
        actions = ActionBar()
        actions.add_leading_button(self.configure_button)
        actions.add_button(self.back_button)
        actions.add_button(self.next_button)
        actions.add_button(self.run_button, primary=True)
        actions.add_button(close_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addLayout(selection)
        layout.addWidget(self.content, 1)
        layout.addWidget(self.empty, 1)
        layout.addWidget(actions)

    @staticmethod
    def _button(text: str) -> QPushButton:
        return QPushButton(text)

    @property
    def current_index(self) -> int:
        return self.stack.currentIndex() if self.panels else -1

    def configure(
        self,
        workflows: dict[str, tuple[AnalysisType, ...]],
        setup: PanelSetup,
        build: ItemBuilder,
    ) -> None:
        self._workflows = dict(workflows)
        self._setup = setup
        self._build = build
        self.choice.blockSignals(True)
        try:
            self.choice.clear()
            for name in sorted(workflows, key=str.casefold):
                self.choice.addItem(name, name)
        finally:
            self.choice.blockSignals(False)
        available = bool(workflows)
        self.choice.setVisible(available)
        self.content.setVisible(available)
        self.empty.setVisible(not available)
        self.configure_button.setVisible(not available)
        if available:
            self._workflow_changed(0)
        else:
            self._clear_panels()
            self._sync_buttons()

    def set_selection_groups(self, use_index: bool, groups: dict[str, int]) -> None:
        for panel in self.panels:
            panel.set_selection_groups(use_index, groups)

    def _workflow_changed(self, index: int) -> None:
        self._clear_panels()
        name = self.choice.itemData(index)
        projects = self._workflows.get(name, ()) if isinstance(name, str) else ()
        panels: list[ParameterPanel] = []
        for number, project in enumerate(projects, start=1):
            panel = ParameterPanel()
            panel.set_analysis_type(project)
            panel.analysis_choice.setEnabled(False)
            self._setup(panel)
            panels.append(panel)
            self.stack.addWidget(panel)
            self.steps.addItem(f"{number}. {analysis_label(project)}")
        self.panels = tuple(panels)
        if panels:
            self._select(0)
        self._sync_buttons()

    def _clear_panels(self) -> None:
        self.panels = ()
        self.steps.clear()
        while self.stack.count():
            panel = self.stack.widget(0)
            if panel is None:
                break
            self.stack.removeWidget(panel)
            panel.deleteLater()

    def _select(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.steps.setCurrentRow(index)
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        index = self.current_index
        last = len(self.panels) - 1
        self.back_button.setEnabled(index > 0)
        self.next_button.setEnabled(0 <= index < last)
        self.run_button.setEnabled(index == last and last >= 0)

    def _back(self) -> None:
        if self.current_index > 0:
            self._select(self.current_index - 1)

    def _next(self) -> None:
        if self.current_index < 0 or self._build is None:
            return
        try:
            self._build(self.panels[self.current_index])
        except Exception as exc:
            self.failed.emit(exc)
            return
        self._select(self.current_index + 1)

    def _run(self) -> None:
        if not self.panels or self._build is None:
            return
        try:
            items = tuple(
                item
                for panel in self.panels
                for item in self._build(panel)
            )
        except Exception as exc:
            self.failed.emit(exc)
            return
        self.run_requested.emit(items)
        self.accept()
