"""Workflow actions for the desktop GUI."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QMainWindow, QMessageBox

from mdhelper.app import ApplicationService
from mdhelper.gui.actions.analysis import AnalysisActions
from mdhelper.gui.actions.backend import BackendActions
from mdhelper.gui.components.parameters import ParameterPanel
from mdhelper.gui.pages.load import LoadPanel
from mdhelper.gui.windows import WindowManager
from mdhelper.gui.workflows.dialog import WorkflowDialog


class WorkflowActions:
    def __init__(
        self,
        parent: QMainWindow,
        application: ApplicationService,
        load: LoadPanel,
        analyses: AnalysisActions,
        backends: BackendActions,
        windows: WindowManager,
        open_config: Callable[[], None],
    ):
        self.parent = parent
        self.application = application
        self.load = load
        self.analyses = analyses
        self.backends = backends
        self.windows = windows
        self.open_config = open_config
        load.selection_inputs_changed.connect(self._selection_changed)

    def open(self) -> None:
        if self.analyses.jobs.running:
            QMessageBox.information(
                self.parent,
                "Run Workflow",
                "Cancel the running analysis before starting a workflow.",
            )
            return
        self.windows.show(
            WorkflowDialog,
            self._configure,
            setup=self._connect,
        )

    def _connect(self, dialog: WorkflowDialog) -> None:
        dialog.run_requested.connect(self.analyses.start)
        dialog.failed.connect(self.analyses.show_error)
        dialog.configure_requested.connect(self.open_config)

    def _configure(self, dialog: WorkflowDialog) -> None:
        dialog.configure(
            self.application.config.workflows,
            self._setup_panel,
            self.analyses.request_items,
        )

    def _setup_panel(self, panel: ParameterPanel) -> None:
        panel.set_selection_groups(
            self.load.inputs.index_value() is not None,
            self.load.index_groups,
        )
        self.backends.attach(panel)

    def _selection_changed(self, use_index: bool, groups: object) -> None:
        dialog = self.windows.get(WorkflowDialog)
        if dialog is not None and isinstance(groups, dict):
            dialog.set_selection_groups(use_index, groups)
