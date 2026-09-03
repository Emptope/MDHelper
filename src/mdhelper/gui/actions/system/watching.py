"""Generated index-file monitoring for the desktop GUI."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMainWindow

from mdhelper.app import ApplicationService
from mdhelper.gui.actions.system.inspection import SystemInspectionActions
from mdhelper.gui.controllers.session import ProjectSession
from mdhelper.gui.pages.analysis import AnalysisPanel
from mdhelper.gui.pages.load import LoadPanel


class FileWatchingActions(SystemInspectionActions):
    def __init__(
        self,
        parent: QMainWindow,
        application: ApplicationService,
        session: ProjectSession,
        load: LoadPanel,
        analysis: AnalysisPanel,
        project_ready: Callable[[str, bool], None],
        show_error: Callable[[BaseException], None],
    ):
        super().__init__(
            parent,
            application,
            session,
            load,
            analysis,
            project_ready,
            show_error,
        )
        self.index_timer = QTimer(parent)
        self.index_timer.setInterval(250)
        self.index_timer.timeout.connect(self.poll_index_file)
        self.index_path: Path | None = None
        self.index_stamp: tuple[int, int] | None = None
        self.index_candidate: tuple[int, int] | None = None

        load.inputs.index_changed.connect(self.index_input_changed)

    def index_input_changed(self) -> None:
        if self.suspend_auto_inspect:
            return
        if self.index_path is not None and self.load.inputs.index_value() != str(
            self.index_path
        ):
            self.cancel_index_watch()
        roles = self.load.species.roles()
        if roles:
            self.state.set_pending_roles(roles)
        self.timer.start()

    @staticmethod
    def _file_stamp(path: Path) -> tuple[int, int] | None:
        try:
            status = path.stat()
        except OSError:
            return None
        return status.st_mtime_ns, status.st_size

    def watch_index_file(self, path: str | Path) -> None:
        self.index_path = Path(path).expanduser().resolve()
        self.index_stamp = self._file_stamp(self.index_path)
        self.index_candidate = None
        self.index_timer.start()

    def cancel_index_watch(self) -> None:
        self.index_timer.stop()
        self.index_path = None
        self.index_stamp = None
        self.index_candidate = None

    def poll_index_file(self) -> None:
        path = self.index_path
        if path is None:
            self.index_timer.stop()
            return
        stamp = self._file_stamp(path)
        if stamp is None or stamp == self.index_stamp:
            self.index_candidate = None
            return
        if stamp != self.index_candidate:
            self.index_candidate = stamp
            return
        self.cancel_index_watch()
        value = str(path)
        if self.load.inputs.index_value() == value:
            self.index_input_changed()
        else:
            self.load.inputs.index_file.set_path(value)

    def shutdown(self) -> None:
        super().shutdown()
        self.cancel_index_watch()
