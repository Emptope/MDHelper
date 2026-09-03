"""Bundled text-template browser for the desktop GUI."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from mdhelper.app import ApplicationService
from mdhelper.gui.components.layout import ActionBar


class TemplatesDialog(QDialog):
    def __init__(self, application: ApplicationService, parent: QWidget | None = None):
        super().__init__(parent)
        self.application = application
        self.setWindowTitle("Templates")
        self.resize(900, 640)
        self.setMinimumSize(700, 480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.template_list = QListWidget()
        self.template_list.currentItemChanged.connect(self._select)
        splitter.addWidget(self.template_list)

        preview = QWidget()
        preview_layout = QVBoxLayout(preview)
        preview_layout.setContentsMargins(12, 0, 0, 0)
        self.title = QLabel()
        self.title.setProperty("role", "heading")
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        preview_layout.addWidget(self.title)
        preview_layout.addWidget(self.text, 1)
        splitter.addWidget(preview)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes((260, 640))
        layout.addWidget(splitter, 1)

        self.copy_button = QPushButton("Copy")
        self.copy_button.clicked.connect(self._copy)
        self.save_button = QPushButton("Save As...")
        self.save_button.clicked.connect(self._save)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        actions = ActionBar()
        actions.add_button(self.copy_button)
        actions.add_button(self.save_button, primary=True)
        actions.add_button(close_button)
        layout.addWidget(actions)

        for template in self.application.templates.list():
            item = QListWidgetItem(f"{template.category} / {template.title}")
            item.setData(Qt.ItemDataRole.UserRole, template.key)
            self.template_list.addItem(item)
        available = self.template_list.count() > 0
        self.copy_button.setEnabled(available)
        self.save_button.setEnabled(available)
        if available:
            self.template_list.setCurrentRow(0)

    def _key(self) -> str | None:
        item = self.template_list.currentItem()
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return value if isinstance(value, str) else None

    def _select(self, current: QListWidgetItem | None, _previous: object = None) -> None:
        if current is None:
            self.title.clear()
            self.text.clear()
            return
        key = self._key()
        if key is None:
            return
        template = self.application.templates.get(key)
        self.title.setText(f"{template.title} ({template.filename})")
        self.text.setPlainText(template.content)

    def _copy(self) -> None:
        key = self._key()
        if key is None:
            return
        QGuiApplication.clipboard().setText(self.application.templates.get(key).content)

    def _save(self) -> None:
        key = self._key()
        if key is None:
            return
        template = self.application.templates.get(key)
        path, _selected_filter = QFileDialog.getSaveFileName(
            self, "Save Template", template.filename, "Text files (*)"
        )
        if not path:
            return
        try:
            saved = self.application.templates.save(key, path)
        except Exception as exc:
            QMessageBox.critical(self, "Template Error", str(exc))
            return
        QMessageBox.information(self, "Template Saved", f"Saved to:\n{saved}")
