"""System-related help windows for the desktop GUI."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QMainWindow

from mdhelper.app import ApplicationService
from mdhelper.gui.actions.system.roles import RoleActions
from mdhelper.gui.controllers.session import ProjectSession
from mdhelper.gui.dialogs.selection import SelectionHintDialog
from mdhelper.gui.dialogs.species import RoleHelpDialog, SuggestionDetailsDialog
from mdhelper.gui.pages.analysis import AnalysisPanel
from mdhelper.gui.pages.load import LoadPanel
from mdhelper.gui.windows import WindowManager


class SystemActions(RoleActions):
    def __init__(
        self,
        parent: QMainWindow,
        application: ApplicationService,
        session: ProjectSession,
        load: LoadPanel,
        analysis: AnalysisPanel,
        windows: WindowManager,
        project_ready: Callable[[str, bool], None],
        show_error: Callable[[BaseException], None],
    ):
        self.windows = windows
        super().__init__(
            parent,
            application,
            session,
            load,
            analysis,
            project_ready,
            show_error,
        )
        load.species.help_requested.connect(self.show_role_help)
        load.species.details_requested.connect(self.show_suggestion_details)
        analysis.selection_hint_requested.connect(self.show_selection_hint)

    def show_role_help(self) -> None:
        self.windows.show(RoleHelpDialog)

    def show_suggestion_details(self, suggestions: object) -> None:
        if not isinstance(suggestions, dict):
            return
        self.windows.show(
            SuggestionDetailsDialog,
            lambda dialog: dialog.set_suggestions(suggestions),
        )

    def show_selection_hint(self, backend: str) -> None:
        self.windows.show(
            SelectionHintDialog,
            lambda dialog: dialog.set_backend(backend),
        )
