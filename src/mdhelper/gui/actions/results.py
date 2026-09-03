"""Result presentation and export actions for the desktop GUI."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox

from mdhelper.app import ApplicationService
from mdhelper.app.analysis import PlotExport, plot_exports, result_exports
from mdhelper.core.plotting import PlotSize
from mdhelper.gui.controllers.session import ProjectSession
from mdhelper.gui.dialogs.results import ResultDetailsDialog
from mdhelper.gui.pages.results import ResultPanel
from mdhelper.gui.plotting.settings import PlotSettingsDialog
from mdhelper.gui.windows import WindowManager


class ResultActions:
    def __init__(
        self,
        parent: QMainWindow,
        application: ApplicationService,
        session: ProjectSession,
        results: ResultPanel,
        windows: WindowManager,
        show_error: Callable[[BaseException], None],
    ):
        self.parent = parent
        self.application = application
        self.session = session
        self.results = results
        self.windows = windows
        self.show_error = show_error

        results.save_project_requested.connect(self.save_project_figures)
        results.export_requested.connect(self.export)
        results.details_requested.connect(self.show_details)
        results.advanced_plot_requested.connect(self.show_plot_settings)

    def show_details(self) -> None:
        result = self.results.result
        if result is None:
            return
        self.windows.show(
            ResultDetailsDialog,
            lambda dialog: dialog.set_content(self.results.context_name(), result),
        )

    def show_plot_settings(self) -> None:
        self.windows.show(
            PlotSettingsDialog,
            lambda dialog: dialog.begin(self.results.plot_appearance()),
            setup=self._connect_plot_settings,
        )

    def export(self) -> None:
        if self.session.result is None:
            QMessageBox.information(
                self.parent,
                "Export",
                "No completed result is available.",
            )
            return
        directory = QFileDialog.getExistingDirectory(
            self.parent, "Export analysis result"
        )
        if not directory:
            return
        plots = self.plot_exports()
        try:
            paths = self.application.exports.export_bundle(
                plots,
                directory,
                self.results.plot_scheme(),
                self.results.plot_limits(),
                self.plot_export_sizes(len(plots)),
                self.results.plot_appearance(),
            )
        except Exception as exc:
            self.show_error(exc)
            return
        QMessageBox.information(
            self.parent,
            "Export Complete",
            f"Exported {len(paths)} files.",
        )

    def save_project_figures(self) -> None:
        if self.session.project is None or self.session.result is None:
            QMessageBox.information(
                self.parent,
                "Project Figures",
                "Open a project and complete an analysis first.",
            )
            return
        plots = self.plot_exports()
        directory = self.session.project.root / "figures"
        try:
            paths = self.application.exports.save_plots(
                plots,
                directory,
                self.results.plot_scheme(),
                self.results.plot_limits(),
                self.plot_export_sizes(len(plots)),
                self.results.plot_appearance(),
            )
        except Exception as exc:
            self.show_error(exc)
            return
        self.parent.statusBar().showMessage(
            f"Saved {len(paths)} figures to {directory}", 10000
        )
        QMessageBox.information(
            self.parent,
            "Project Figures Saved",
            f"Saved PNG, SVG, and PDF to:\n{directory}",
        )

    def plot_exports(self) -> tuple[PlotExport, ...]:
        visible = self.results.plot_results()
        if visible:
            return plot_exports(
                visible,
                series_keys=self.results.plot_series_keys(),
                labels=self.results.plot_labels(),
                color_ids=self.results.plot_color_ids(),
                group_ids=self.results.plot_group_ids(),
                titles=self.results.plot_titles(),
            )
        if self.session.result is None:
            raise RuntimeError("No completed result is available.")
        items = result_exports(self.session.result)
        return plot_exports(tuple(item.result for item in items))

    def plot_export_sizes(self, count: int) -> tuple[PlotSize, ...]:
        sizes = self.results.plot_sizes()
        if len(sizes) == count:
            return sizes
        size = self.results.plot_size()
        return tuple(size for _index in range(count))

    def _connect_plot_settings(self, dialog: PlotSettingsDialog) -> None:
        dialog.applied.connect(self.results.apply_plot_appearance)
        dialog.reverted.connect(self.results.apply_plot_appearance)
