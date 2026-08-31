"""Reusable ordered item queues for GUI parameter forms."""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ItemQueue(QWidget):
    """Move unique strings from an available list into an ordered queue."""

    def __init__(
        self,
        available_label: str,
        queue_label: str,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.available = QListWidget()
        self.queue = QListWidget()
        for control in (self.available, self.queue):
            control.setSelectionMode(
                QAbstractItemView.SelectionMode.ExtendedSelection
            )
            control.setMinimumHeight(170)
        self.add_button = QPushButton("Add")
        self.add_all_button = QPushButton("Add All")
        self.remove_button = QPushButton("Remove")
        self.clear_button = QPushButton("Clear All")
        self.add_button.clicked.connect(self.add_selected)
        self.add_all_button.clicked.connect(self.add_all)
        self.remove_button.clicked.connect(self.remove_selected)
        self.clear_button.clicked.connect(self.clear)
        self.available.itemDoubleClicked.connect(lambda _item: self.add_selected())
        self.queue.itemDoubleClicked.connect(lambda _item: self.remove_selected())

        actions = QVBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)
        actions.addStretch(1)
        actions.addWidget(self.add_button)
        actions.addWidget(self.add_all_button)
        actions.addWidget(self.remove_button)
        actions.addWidget(self.clear_button)
        actions.addStretch(1)

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(6)
        layout.addWidget(QLabel(available_label), 0, 0)
        layout.addWidget(QLabel(queue_label), 0, 2)
        layout.addWidget(self.available, 1, 0)
        layout.addLayout(actions, 1, 1)
        layout.addWidget(self.queue, 1, 2)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(2, 1)

    def set_available(self, items: Iterable[str]) -> None:
        values = tuple(dict.fromkeys(item.strip() for item in items if item.strip()))
        self.available.clear()
        self.available.addItems(values)

    def set_items(self, items: Iterable[str]) -> None:
        values = tuple(dict.fromkeys(item.strip() for item in items if item.strip()))
        self.queue.clear()
        self.queue.addItems(values)

    def items(self) -> tuple[str, ...]:
        return tuple(self.queue.item(index).text() for index in range(self.queue.count()))

    def add_selected(self) -> None:
        rows = sorted({self.available.row(item) for item in self.available.selectedItems()})
        self._add(self.available.item(row).text() for row in rows)

    def add_all(self) -> None:
        self._add(
            self.available.item(index).text()
            for index in range(self.available.count())
        )

    def remove_selected(self) -> None:
        rows = sorted({self.queue.row(item) for item in self.queue.selectedItems()}, reverse=True)
        for row in rows:
            self.queue.takeItem(row)

    def clear(self) -> None:
        self.queue.clear()

    def clear_all(self) -> None:
        self.available.clear()
        self.queue.clear()

    def _add(self, items: Iterable[str]) -> None:
        existing = set(self.items())
        for item in items:
            if item not in existing:
                self.queue.addItem(item)
                existing.add(item)
