"""Frame-range controls shared by trajectory analyses."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QGroupBox, QLabel, QLineEdit, QSpinBox, QWidget

from mdhelper.core.system import FrameRange


class FrameRangeParameters(QGroupBox):
    """Edit a zero-based, stop-exclusive trajectory frame range."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__("Frame Sampling", parent)
        self.start = QSpinBox()
        self.start.setRange(0, 2_000_000_000)
        self.stop = QLineEdit()
        self.stop.setPlaceholderText("end")
        self.stride = QSpinBox()
        self.stride.setRange(1, 2_000_000_000)
        self.stride.setValue(1)
        self.start.valueChanged.connect(lambda _value: self.changed.emit())
        self.stop.editingFinished.connect(self.changed.emit)
        self.stride.valueChanged.connect(lambda _value: self.changed.emit())

        grid = QGridLayout(self)
        grid.setContentsMargins(12, 10, 12, 10)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        grid.addWidget(QLabel("First frame (0-based)"), 0, 0)
        grid.addWidget(self.start, 0, 1)
        grid.addWidget(QLabel("Stop frame (exclusive)"), 0, 2)
        grid.addWidget(self.stop, 0, 3)
        grid.addWidget(QLabel("Stride (frames)"), 1, 0)
        grid.addWidget(self.stride, 1, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

    def value(self) -> FrameRange:
        stop_text = self.stop.text().strip()
        return FrameRange(
            start=self.start.value(),
            stop=None if not stop_text else int(stop_text),
            stride=self.stride.value(),
        )

    def apply(self, frames: FrameRange) -> None:
        self.start.setValue(frames.start)
        self.stop.setText("" if frames.stop is None else str(frames.stop))
        self.stride.setValue(frames.stride)

    def reset(self) -> None:
        self.start.setValue(0)
        self.stop.clear()
        self.stride.setValue(1)
