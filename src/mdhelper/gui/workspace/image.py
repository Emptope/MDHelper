"""Viewport-sized image display with one outstanding decode request."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPainter, QPaintEvent, QResizeEvent, QShowEvent
from PySide6.QtWidgets import QWidget

from mdhelper.core.workspace import ImageInfo, ImagePixels


class ImageView(QWidget):
    requested = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.source: ImageInfo | None = None
        self.pixels = QImage()
        self._pending = False
        self._size: tuple[int, int] | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._request)

    def set_source(self, source: ImageInfo) -> None:
        self.clear()
        self.source = source
        self._timer.start()

    def clear(self) -> None:
        self._timer.stop()
        self.source = None
        self.pixels = QImage()
        self._pending = False
        self._size = None
        self.update()

    def set_pixels(self, pixels: ImagePixels) -> None:
        self._pending = False
        self.pixels = QImage(
            pixels.rgba, pixels.width, pixels.height, pixels.width * 4,
            QImage.Format.Format_RGBA8888,
        ).copy()
        self.update()
        self._timer.start()

    def _request(self) -> None:
        size = (max(1, min(self.width(), 2048)), max(1, min(self.height(), 2048)))
        if (self.source is not None and self.isVisible()
                and not self._pending and size != self._size):
            self._size = size
            self._pending = True
            self.requested.emit(size)

    def sizeHint(self) -> QSize:
        return QSize(320, 240)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._timer.start()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._timer.start()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().base())
        if not self.pixels.isNull():
            size = self.pixels.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
            rect = self.rect()
            rect.setSize(size)
            rect.moveCenter(self.rect().center())
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawImage(rect, self.pixels)
        painter.end()
