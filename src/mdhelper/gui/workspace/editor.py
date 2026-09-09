"""Folder explorer and file details page."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import cast

from PySide6.QtCore import QDir, QModelIndex, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence, QTextCursor
from PySide6.QtWidgets import (
    QFileDialog,
    QFileSystemModel,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from mdhelper.core.errors import JobCancelled
from mdhelper.core.workspace import DataPage, ImagePixels, WorkspaceFile
from mdhelper.gui.components.layout import page_layout
from mdhelper.gui.workspace.data import DataView
from mdhelper.gui.workspace.image import ImageView
from mdhelper.gui.workspace.text import FileTextEditor
from mdhelper.gui.workspace.worker import DocumentWorker
from mdhelper.services.workspace import save_workspace_text


class WorkspaceEditor(QWidget):
    error_reported = Signal(object)
    open_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.root: Path | None = None
        self.current_path: str | None = None
        self._loading_path: str | None = None
        self._resume_path: str | None = None
        self._exporting = False
        self._exportable = False
        self.worker = DocumentWorker(self)
        self.empty = QWidget()
        empty_layout = QVBoxLayout(self.empty)
        empty_layout.addStretch()
        hint = QLabel("Open a folder to explore files")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(hint)
        self.open_project = QPushButton("Open Project")
        empty_layout.addWidget(self.open_project, alignment=Qt.AlignmentFlag.AlignHCenter)
        empty_layout.addStretch()
        self.open_project.clicked.connect(self.open_requested)

        self.files = QFileSystemModel(self)
        self.files.setFilter(
            QDir.Filter.AllEntries | QDir.Filter.NoDotAndDotDot | QDir.Filter.Hidden
        )
        self.tree = QTreeView()
        self.tree.setModel(self.files)
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumWidth(self.tree.fontMetrics().averageCharWidth() * 18)
        self.tree.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
        for column in range(1, self.files.columnCount()):
            self.tree.hideColumn(column)
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.tree.selectionModel().currentChanged.connect(self._selected)

        details = QWidget()
        detail_layout = QVBoxLayout(details)
        self.info = QLabel()
        self.info.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.info.setTextFormat(Qt.TextFormat.PlainText)
        self.info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.export_button = QPushButton("Export Text...")
        self.export_button.setToolTip(
            "Export all frames of the selected data as CSV or TXT"
        )
        self.save_button = QPushButton("Save")
        self.cancel_button = QPushButton("Cancel")
        controls = QHBoxLayout()
        controls.addWidget(self.info, 1)
        controls.addWidget(self.export_button)
        controls.addWidget(self.save_button)
        controls.addWidget(self.cancel_button)
        detail_layout.addLayout(controls)
        self.status = QLabel("Select a file")
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.editor = FileTextEditor()
        self.editor.setReadOnly(True)
        self.data = DataView()
        self.image = ImageView()
        self.content = QStackedWidget()
        self.content.addWidget(self.editor)
        self.content.addWidget(self.data)
        self.content.addWidget(self.image)
        detail_layout.addWidget(self.content, 1)
        self.cursor_position = QLabel()
        self.cursor_position.setAccessibleName("Cursor position")
        self.cursor_position.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred,
        )
        self.cursor_position.setToolTip(
            "Line and column start at 1. Tabs span 4 columns; "
            "Unicode code points and line breaks count as one selected character."
        )
        footer = QHBoxLayout()
        footer.addWidget(self.status, 1)
        footer.addWidget(self.cursor_position)
        detail_layout.addLayout(footer)
        self.editor.cursorPositionChanged.connect(self._update_cursor_position)
        self.editor.selectionChanged.connect(self._update_cursor_position)
        self.editor.textChanged.connect(self._update_cursor_position)
        self.content.currentChanged.connect(self._update_cursor_position)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self.tree)
        self.splitter.addWidget(details)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes((230, 630))
        self.stack = QStackedWidget()
        self.stack.addWidget(self.empty)
        self.stack.addWidget(self.splitter)
        page_layout(self).addWidget(self.stack)
        self.save_button.clicked.connect(self.save)
        self.export_button.clicked.connect(self.export_text)
        self.cancel_button.clicked.connect(self.cancel)
        self.save_action = QAction("Save", self)
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.save_action.triggered.connect(self.save)
        self.addAction(self.save_action)
        self.editor.modificationChanged.connect(self._update_save_state)
        self.worker.opened.connect(self._opened)
        self.worker.paged.connect(self._paged)
        self.worker.imaged.connect(self._imaged)
        self.worker.failed.connect(self._failed)
        self.worker.exported.connect(self._exported)
        self.worker.export_failed.connect(self._export_failed)
        self.data.model.page_requested.connect(self._load_page)
        self.data.selection_changed.connect(self._update_save_state)
        self.image.requested.connect(self._load_image)
        self.cancel_button.hide()
        self._update_save_state()
        self._update_cursor_position()

    def set_root(self, path: str | Path | None) -> bool:
        if not self.confirm_discard():
            return False
        root = None if path is None else Path(path).expanduser().resolve()
        if root is not None and not root.is_dir():
            raise NotADirectoryError(root)
        self.clear()
        self.root = root
        self.stack.setCurrentWidget(self.empty if root is None else self.splitter)
        if root is not None:
            self.tree.setRootIndex(self.files.setRootPath(str(root)))
        return True

    def clear(self) -> None:
        self.worker.cancel()
        self._exporting = False
        self._exportable = False
        self.current_path = None
        self._loading_path = None
        self._resume_path = None
        self.editor.clear()
        self.editor.setReadOnly(True)
        self.editor.document().setModified(False)
        self.image.clear()
        self.data.configure(0)
        self.content.setCurrentWidget(self.editor)
        self.info.clear()
        self.info.setToolTip("")
        self.status.setToolTip("")
        self.status.setText("Select a file")
        self.cancel_button.hide()
        self._update_save_state()

    def _selected(self, current: QModelIndex, previous: QModelIndex) -> None:
        if not current.isValid() or self.files.isDir(current):
            return
        if not self.open_path(self.files.filePath(current)):
            selection = self.tree.selectionModel()
            selection.blockSignals(True)
            self.tree.setCurrentIndex(previous)
            selection.blockSignals(False)

    def open_path(self, path: str) -> bool:
        if not self.confirm_discard():
            return False
        self.clear()
        source = Path(path).expanduser().resolve()
        selection = self.tree.selectionModel()
        blocked = selection.blockSignals(True)
        try:
            # Keep delayed focus events from selecting a different file.
            self.tree.setCurrentIndex(self.files.index(str(source)))
        finally:
            selection.blockSignals(blocked)
        self.info.setText(Path(path).name)
        self.info.setToolTip(str(source))
        self.status.setText("Reading file...")
        self.cancel_button.show()
        self._loading_path = path
        self.worker.open(path)
        return True

    def suspend(self) -> None:
        if self._loading_path is not None:
            self._resume_path = self._loading_path
        elif self.content.currentWidget() in (self.data, self.image):
            self._resume_path = self.current_path
        self.worker.cancel()
        self._exporting = False
        self._exportable = False
        self._update_save_state()
        self._loading_path = None
        self.data.configure(0)
        self.image.clear()
        self.cancel_button.hide()
        if self._resume_path is not None:
            self.status.setText("Reading paused")

    def resume(self) -> None:
        if self._resume_path is not None:
            self.open_path(self._resume_path)

    def _opened(self, result: object) -> None:
        file, rows = cast(tuple[WorkspaceFile, int], result)
        self._loading_path = None
        try:
            self.set_file(file)
        except OSError as exc:
            self._failed(exc)
            return
        self.cancel_button.hide()
        if file.image is not None:
            self.content.setCurrentWidget(self.image)
            self.image.set_source(file.image)
        elif file.parsed:
            self.content.setCurrentWidget(self.data)
            self.data.configure(rows, file.layout)
            self.data.model.fetchMore()

    def _load_page(self, offset: int) -> None:
        self.cancel_button.show()
        self.worker.page(offset)

    def _paged(self, page: DataPage) -> None:
        self.data.model.set_page(page)
        self.cancel_button.setVisible(self._exporting or self.data.model.loading)

    def _load_image(self, size: tuple[int, int]) -> None:
        self.cancel_button.show()
        self.worker.image(size)

    def _imaged(self, pixels: ImagePixels) -> None:
        self.image.set_pixels(pixels)
        self.cancel_button.setVisible(self._exporting)

    def set_file(self, file: WorkspaceFile) -> None:
        self.current_path = file.path
        self._exportable = file.parsed
        self.editor.setPlainText(file.text)
        self.editor.setReadOnly(not file.editable)
        self.editor.document().setModified(False)
        source = Path(file.path)
        stat = source.stat()
        modified = datetime.fromtimestamp(stat.st_mtime).isoformat(sep=" ", timespec="seconds")
        self.info.setText(source.name)
        self.info.setToolTip(f"{source}\n{stat.st_size} bytes\n{modified}")
        readable = file.editable or bool(file.text) or file.parsed or file.image is not None
        summary = file.message if readable else "Cannot parse this format"
        metadata = f"{stat.st_size} bytes | Modified {modified}"
        self.status.setText(f"{metadata} | {summary}")
        self.status.setToolTip(f"{metadata}\n{file.message}")
        self._update_save_state()
        self._update_cursor_position()

    def save(self) -> bool:
        if self.current_path is None or self.editor.isReadOnly():
            return False
        try:
            self.set_file(save_workspace_text(self.current_path, self.editor.toPlainText()))
            return True
        except Exception as exc:
            self.error_reported.emit(exc)
            return False

    def export_text(self) -> None:
        if (
            not self._exportable or self.current_path is None or self._exporting
            or not self.data.has_selected_terms()
        ):
            return
        columns = self.data.export_columns()
        target, selected_filter = QFileDialog.getSaveFileName(
            self, "Export Parsed Data", f"{self.current_path}.csv",
            "CSV files (*.csv);;Text files (*.txt)",
        )
        if not target:
            return
        if not Path(target).suffix:
            target += ".txt" if selected_filter == "Text files (*.txt)" else ".csv"
            # Qt normally appends the suffix before confirming an overwrite.
            # Check again when a platform dialog returns an extensionless name.
            if Path(target).exists() and QMessageBox.question(
                self, "Overwrite File?", f"Replace {Path(target).name}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            ) != QMessageBox.StandardButton.Yes:
                return
        self._exporting = True
        self._update_save_state()
        self.status.setText("Exporting parsed data...")
        self.cancel_button.show()
        self.worker.export(self.current_path, target, columns)

    def _exported(self, target: Path) -> None:
        self._exporting = False
        self._update_save_state()
        self.cancel_button.setVisible(self.data.model.loading)
        self.status.setText(f"Exported: {target.name}")
        self.status.setToolTip(str(target))

    def _export_failed(self, error: BaseException) -> None:
        self._exporting = False
        self._update_save_state()
        self.cancel_button.setVisible(self.data.model.loading)
        cancelled = isinstance(error, JobCancelled)
        self.status.setText("Export cancelled" if cancelled else "Could not export data")
        if not cancelled:
            self.status.setToolTip(str(error))
            self.error_reported.emit(error)

    def confirm_discard(self) -> bool:
        if not self.editor.document().isModified():
            return True
        answer = QMessageBox.question(
            self, "Unsaved changes", "Save changes before continuing?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Save:
            return self.save()
        return answer == QMessageBox.StandardButton.Discard

    def cancel(self) -> None:
        if self._exporting:
            self.worker.cancel_export()
        else:
            self.clear()

    def _failed(self, error: BaseException) -> None:
        self.worker.cancel()
        self._exporting = False
        self._exportable = False
        self._update_save_state()
        self._loading_path = None
        self._resume_path = None
        self.data.configure(0)
        self.image.clear()
        self.cancel_button.hide()
        self.status.setText("Could not read file")
        self.status.setToolTip(str(error))
        self.error_reported.emit(error)

    def _update_cursor_position(self) -> None:
        cursor = self.editor.textCursor()
        prefix = QTextCursor(cursor)
        prefix.clearSelection()
        prefix.setPosition(cursor.block().position(), QTextCursor.MoveMode.KeepAnchor)
        column = len(prefix.selectedText().expandtabs(4)) + 1
        position = f"Ln {cursor.blockNumber() + 1}, Col {column}"
        if cursor.hasSelection():
            position += f" | {len(cursor.selectedText())} selected"
        self.cursor_position.setText(position)
        self.cursor_position.setVisible(
            self.current_path is not None and self.content.currentWidget() is self.editor
        )

    def _update_save_state(self) -> None:
        self.export_button.setVisible(self._exportable)
        self.export_button.setEnabled(
            self._exportable and not self._exporting and self.data.has_selected_terms()
        )
        editable = self.current_path is not None and not self.editor.isReadOnly()
        self.save_button.setEnabled(editable)
        self.save_button.setVisible(editable)
        self.save_action.setEnabled(editable)

    def shutdown(self) -> None:
        self.worker.shutdown()


__all__ = ["WorkspaceEditor"]
