"""Main workspace pages for the desktop GUI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QTabWidget, QWidget

from mdhelper.gui.pages.analysis import AnalysisPanel
from mdhelper.gui.pages.load import LoadPanel
from mdhelper.gui.pages.results import ResultPanel

if TYPE_CHECKING:
    from mdhelper.gui.windows import WindowManager


class WorkspaceTabs(QTabWidget):
    """Own the stable tab order and page instances used by the main window."""

    def __init__(
        self,
        parent: QWidget | None = None,
        windows: WindowManager | None = None,
    ):
        super().__init__(parent)
        self.setDocumentMode(True)
        self.setMovable(False)
        self.load = LoadPanel()
        self.analysis = AnalysisPanel()
        self.results = ResultPanel(windows=windows)
        self.addTab(self.load, "Load")
        self.addTab(self.analysis, "Analysis")
        self.addTab(self.results, "Result")
