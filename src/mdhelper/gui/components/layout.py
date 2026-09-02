"""Shared layout primitives for consistent desktop GUI composition."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

PAGE_MARGIN = 16
PAGE_SPACING = 12


def page_layout(parent: QWidget) -> QVBoxLayout:
    """Create the standard top-level layout used by GUI pages."""

    layout = QVBoxLayout(parent)
    layout.setContentsMargins(PAGE_MARGIN, PAGE_MARGIN, PAGE_MARGIN, PAGE_MARGIN)
    layout.setSpacing(PAGE_SPACING)
    return layout


def configure_form(form: QFormLayout) -> None:
    """Apply the compact spacing shared by parameter forms."""

    form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
    form.setHorizontalSpacing(14)
    form.setVerticalSpacing(10)


def configure_button(
    button: QPushButton,
    primary: bool = False,
    compact: bool = False,
) -> QPushButton:
    """Apply consistent geometry and visual emphasis to an action button."""

    if compact:
        button.setFixedHeight(24)
    else:
        button.setMinimumHeight(28)
    button.setProperty("importance", "primary" if primary else "secondary")
    return button


class ActionBar(QFrame):
    """Compact flat action row with optional context and right-aligned controls."""

    def __init__(
        self,
        title: str = "",
        parent: QWidget | None = None,
        stacked: bool = False,
    ):
        super().__init__(parent)
        self.stacked = stacked
        self.setObjectName("actionBar")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.title = QLabel(title)
        self.title.setVisible(bool(title))
        self.action_layout = QHBoxLayout()
        self.action_layout.setContentsMargins(0, 0, 0, 0)
        self.action_layout.setSpacing(8)
        if stacked:
            stacked_layout = QVBoxLayout(self)
            stacked_layout.setContentsMargins(0, 2, 0, 2)
            stacked_layout.setSpacing(8)
            controls = QHBoxLayout()
            controls.setContentsMargins(0, 0, 0, 0)
            controls.setSpacing(8)
            controls.addWidget(self.title)
            controls.addStretch(1)
            controls.addLayout(self.action_layout)
            stacked_layout.addLayout(controls)
            self.widget_layout = QHBoxLayout()
            self.widget_layout.setContentsMargins(0, 0, 0, 0)
            self.widget_layout.setSpacing(8)
            stacked_layout.addLayout(self.widget_layout)
        else:
            row_layout = QHBoxLayout(self)
            row_layout.setContentsMargins(0, 2, 0, 2)
            row_layout.setSpacing(8)
            row_layout.addWidget(self.title)
            row_layout.addStretch(1)
            row_layout.addLayout(self.action_layout)
            self.widget_layout = self.action_layout

    def add_button(self, button: QPushButton, primary: bool = False) -> None:
        configure_button(button, primary)
        self.action_layout.addWidget(button)

    def add_widget(self, widget: QWidget, stretch: int = 0) -> None:
        self.widget_layout.addWidget(widget, stretch)
