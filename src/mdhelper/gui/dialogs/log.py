"""Non-modal raw log viewer for the latest analysis job."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mdhelper.gui.components.layout import ActionBar


class JobLogDialog(QDialog):
    """Display and copy messages without blocking the main window."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, True)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, True)
        self.setWindowTitle("Job Log")
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.resize(720, 460)
        self.setMinimumSize(520, 320)
        self._job_id = ""
        self._messages: tuple[str, ...] = ()
        self.copy_notice: QMessageBox | None = None

        self.header = ActionBar()
        self.heading = self.header.title
        self.heading.setProperty("role", "heading")
        self.heading.setVisible(True)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        self.copy_button = QPushButton("Copy")
        self.copy_button.clicked.connect(self._copy)
        actions = ActionBar()
        actions.add_button(self.copy_button, primary=True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(self.header)
        layout.addWidget(self.log, 1)
        layout.addWidget(actions)

    def set_content(
        self,
        job_id: str,
        name: str,
        messages: Sequence[str],
    ) -> None:
        updated = tuple(messages)
        scroll = self.log.verticalScrollBar()
        previous_position = scroll.value()
        new_job = job_id != self._job_id
        follow = (
            new_job
            or not self.isVisible()
            or previous_position >= scroll.maximum()
        )
        self.heading.setText(name)
        incremental = (
            not new_job
            and len(updated) >= len(self._messages)
            and updated[: len(self._messages)] == self._messages
        )
        if incremental:
            additions = updated[len(self._messages) :]
            if additions:
                self.log.appendPlainText("\n".join(additions))
        else:
            self.log.setPlainText("\n".join(updated))
        self._job_id = job_id
        self._messages = updated
        self.copy_button.setEnabled(bool(updated))
        if follow:
            self.log.moveCursor(QTextCursor.MoveOperation.End)
            self.log.ensureCursorVisible()
            scroll.setValue(scroll.maximum())
        else:
            scroll.setValue(min(previous_position, scroll.maximum()))

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self.log.toPlainText())
        if self.copy_notice is None:
            self.copy_notice = QMessageBox(self)
            self.copy_notice.setIcon(QMessageBox.Icon.Information)
            self.copy_notice.setWindowTitle("Log Copied")
            self.copy_notice.setText("Log copied to clipboard.")
            self.copy_notice.setStandardButtons(QMessageBox.StandardButton.Ok)
            self.copy_notice.setWindowModality(Qt.WindowModality.NonModal)
        self.copy_notice.show()
        self.copy_notice.raise_()
        self.copy_notice.activateWindow()
