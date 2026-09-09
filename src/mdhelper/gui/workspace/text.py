"""Plain-text file editor with a scalable font and a line-number gutter."""

from __future__ import annotations

from typing import cast

from PySide6.QtCore import QEvent, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QFont, QFontDatabase, QPainter, QPaintEvent, QResizeEvent
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QWidget

_GUTTER_LEFT_PADDING = 8
_GUTTER_RIGHT_PADDING = 16


class _LineNumbers(QWidget):
    def __init__(self, editor: FileTextEditor):
        super().__init__(editor)
        self.setAccessibleName("Line numbers")

    @property
    def editor(self) -> FileTextEditor:
        # Do not retain the parent in a Python reference cycle: Qt owns us.
        return cast(FileTextEditor, self.parentWidget())

    def sizeHint(self) -> QSize:
        return QSize(self.editor.line_number_width(), 0)

    def paintEvent(self, event: QPaintEvent) -> None:
        self.editor.paint_line_numbers(event)


class FileTextEditor(QPlainTextEdit):
    """Keep file text unchanged; numbers are painted outside the document."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.line_numbers = _LineNumbers(self)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.blockCountChanged.connect(self._update_margin)
        self.updateRequest.connect(self._update_numbers)
        self.cursorPositionChanged.connect(self.line_numbers.update)
        self._setting_font = False
        self._font_timer = QTimer(self)
        self._font_timer.setSingleShot(True)
        self._font_timer.timeout.connect(self._set_editor_font)
        app = QApplication.instance()
        if isinstance(app, QApplication):
            # Run after the theme controller refreshes Qt's stylesheet font cache.
            app.fontChanged.connect(self._schedule_font)
            self._set_editor_font()
        self._update_margin()

    def setReadOnly(self, read_only: bool) -> None:
        super().setReadOnly(read_only)
        if read_only:
            self.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
                | Qt.TextInteractionFlag.TextSelectableByKeyboard
            )

    def _schedule_font(self, _font: QFont) -> None:
        self._font_timer.start(0)

    def _set_editor_font(self) -> None:
        application_font = QApplication.font()
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setPointSizeF(max(14.0, application_font.pointSizeF()))
        self._setting_font = True
        try:
            self.setFont(font)
            self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        finally:
            self._setting_font = False

    def line_number_width(self) -> int:
        digits = len(str(max(1, self.blockCount())))
        return (
            self.fontMetrics().horizontalAdvance("9") * digits
            + _GUTTER_LEFT_PADDING + _GUTTER_RIGHT_PADDING
        )

    def _update_margin(self, _count: int = 0) -> None:
        width = self.line_number_width()
        self.setViewportMargins(width, 0, 0, 0)
        viewport = self.viewport().geometry()
        self.line_numbers.setGeometry(
            viewport.left() - width, viewport.top(), width, viewport.height(),
        )
        self.line_numbers.update()

    def _update_numbers(self, rect: QRect, dy: int) -> None:
        if dy:
            self.line_numbers.scroll(0, dy)
        else:
            self.line_numbers.update(0, rect.y(), self.line_numbers.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_margin()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_margin()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        # QWidget construction can send events before the gutter exists.
        if hasattr(self, "line_numbers") and event.type() in (
            QEvent.Type.FontChange, QEvent.Type.StyleChange, QEvent.Type.PaletteChange,
        ):
            self._update_margin()
            if hasattr(self, "_font_timer") and not self._setting_font:
                # A stylesheet repolish can restore a cached font even when
                # QApplication's font has not changed. Restore our editor font.
                self._font_timer.start(0)

    def paint_line_numbers(self, event: QPaintEvent) -> None:
        painter = QPainter(self.line_numbers)
        palette = self.palette()
        painter.fillRect(event.rect(), palette.alternateBase())
        painter.setFont(self.font())
        block = self.firstVisibleBlock()
        current = self.textCursor().blockNumber()
        while block.isValid():
            top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
            height = self.blockBoundingRect(block).height()
            if top > event.rect().bottom():
                break
            if block.isVisible() and top + height >= event.rect().top():
                painter.setPen(
                    palette.text().color() if block.blockNumber() == current
                    else palette.placeholderText().color()
                )
                painter.drawText(
                    0, round(top), self.line_numbers.width() - _GUTTER_RIGHT_PADDING,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
                    str(block.blockNumber() + 1),
                )
            block = block.next()
        painter.end()
