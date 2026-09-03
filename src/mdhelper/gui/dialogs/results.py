"""Detailed result viewer for the desktop GUI."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from mdhelper.core.analysis import AnalysisResult
from mdhelper.gui.components.layout import ActionBar
from mdhelper.gui.formatting import result_details_html


class ResultDetailsDialog(QDialog):
    """Display and copy the complete report for one result."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Result Details")
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.resize(720, 520)
        self.setMinimumSize(520, 340)
        self.copy_notice: QMessageBox | None = None

        self.header = ActionBar()
        self.heading = self.header.title
        self.heading.setProperty("role", "heading")
        self.heading.setVisible(True)
        self.text = QTextBrowser()
        self.text.setReadOnly(True)
        self.text.setOpenExternalLinks(False)

        self.copy_button = QPushButton("Copy")
        self.copy_button.clicked.connect(self._copy)
        actions = ActionBar()
        actions.add_button(self.copy_button, primary=True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(self.header)
        layout.addWidget(self.text, 1)
        layout.addWidget(actions)

    def set_content(self, name: str, result: AnalysisResult) -> None:
        self.heading.setText(name)
        self.text.setHtml(result_details_html(result))
        self.copy_button.setEnabled(bool(self.text.toPlainText()))

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self.text.toPlainText())
        if self.copy_notice is None:
            self.copy_notice = QMessageBox(self)
            self.copy_notice.setIcon(QMessageBox.Icon.Information)
            self.copy_notice.setWindowTitle("Result Copied")
            self.copy_notice.setText("Result details copied to clipboard.")
            self.copy_notice.setStandardButtons(QMessageBox.StandardButton.Ok)
            self.copy_notice.setWindowModality(Qt.WindowModality.NonModal)
        self.copy_notice.show()
        self.copy_notice.raise_()
        self.copy_notice.activateWindow()
