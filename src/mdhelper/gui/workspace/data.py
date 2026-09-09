"""Continuous read-only data table with a bounded page cache."""

from __future__ import annotations

from collections import OrderedDict

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from mdhelper.core.workspace import DATA_COLUMNS, DataLayout, DataPage

_ROOT = QModelIndex()


class DataModel(QAbstractTableModel):
    page_requested = Signal(int)
    page_size = 256
    cache_size = 8

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.rows = 0
        self.columns: tuple[str, ...] = DATA_COLUMNS
        self._pages: OrderedDict[int, DataPage] = OrderedDict()
        self._pending: set[int] = set()
        self._more = False
        self._fetching: int | None = None

    def configure(
        self, rows: int, columns: tuple[str, ...] = DATA_COLUMNS, streaming: bool = False,
    ) -> None:
        self.beginResetModel()
        self.rows = rows
        self.columns = columns
        self._pages.clear()
        self._pending.clear()
        self._more = streaming
        self._fetching = None
        self.endResetModel()

    def set_page(self, page: DataPage) -> None:
        self._pending.discard(page.offset)
        if self._fetching == page.offset:
            self._fetching = None
        self._more = self._more and not page.complete
        if page.section.rows > self.rows:
            self.beginInsertRows(_ROOT, self.rows, page.section.rows - 1)
            self.rows = page.section.rows
            self.endInsertRows()
        self._pages[page.offset] = page
        self._pages.move_to_end(page.offset)
        while len(self._pages) > self.cache_size:
            self._pages.popitem(last=False)
        if page.rows:
            self.dataChanged.emit(
                self.index(page.offset, 0),
                self.index(page.offset + len(page.rows) - 1, len(self.columns) - 1),
            )

    def canFetchMore(self, parent: QModelIndex | QPersistentModelIndex = _ROOT) -> bool:
        return not parent.isValid() and self._more and self._fetching is None

    def fetchMore(self, parent: QModelIndex | QPersistentModelIndex = _ROOT) -> None:
        if self.canFetchMore(parent):
            self._fetching = self.rows // self.page_size * self.page_size
            self._request(self._fetching)

    def _request(self, offset: int) -> None:
        if offset not in self._pending:
            self._pending.add(offset)
            self.page_requested.emit(offset)

    @property
    def loading(self) -> bool:
        return bool(self._pending)

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = _ROOT) -> int:
        return 0 if parent.isValid() else self.rows

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = _ROOT) -> int:
        return 0 if parent.isValid() else len(self.columns)

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = 0) -> object:
        if not index.isValid() or role not in (
            Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole,
        ):
            return None
        offset = index.row() // self.page_size * self.page_size
        page = self._pages.get(offset)
        if page is None:
            if offset not in self._pending and len(self._pending) < self.cache_size:
                self._request(offset)
            return None
        self._pages.move_to_end(offset)
        row = index.row() - offset
        return page.rows[row][index.column()] if row < len(page.rows) else None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = 0) -> object:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        return self.columns[section] if orientation == Qt.Orientation.Horizontal else str(section)


class DataView(QWidget):
    def __init__(self):
        super().__init__()
        self.table = QTableView()
        self.model = DataModel(self)
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setColumnWidth(0, 250)
        self.table.setColumnWidth(1, 70)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(self._details)
        self.selector = QWidget()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Find items")
        self.items = QListWidget()
        self.items.itemChanged.connect(self._select_item)
        self.search.textChanged.connect(self._filter_items)
        selector_layout = QVBoxLayout(self.selector)
        selector_layout.setContentsMargins(0, 0, 0, 0)
        selector_layout.addWidget(self.search)
        selector_layout.addWidget(self.items)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.selector)
        splitter.addWidget(self.table)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes((200, 600))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)
        self.selector.hide()

    def configure(self, rows: int, layout: DataLayout | None = None) -> None:
        if layout is None:
            layout = DataLayout()
        self.model.configure(rows, layout.columns, layout.streaming)
        self.items.clear()
        self.search.clear()
        self.selector.setVisible(bool(layout.selectable))
        self.table.verticalHeader().setVisible(not layout.selectable)
        for column in range(len(layout.columns)):
            self.table.setColumnHidden(column, False)
            if layout.selectable:
                self.table.setColumnWidth(column, 80 if column == 0 else 160)
        for index, column in enumerate(layout.selectable):
            item = QListWidgetItem(layout.columns[column])
            item.setData(Qt.ItemDataRole.UserRole, column)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if index == 0 else Qt.CheckState.Unchecked)
            self.items.addItem(item)
            self._select_item(item)

    def _select_item(self, item: QListWidgetItem) -> None:
        self.table.setColumnHidden(
            item.data(Qt.ItemDataRole.UserRole), item.checkState() != Qt.CheckState.Checked,
        )

    def _filter_items(self, text: str) -> None:
        for index in range(self.items.count()):
            item = self.items.item(index)
            item.setHidden(text.casefold() not in item.text().casefold())

    def _details(self, index: QModelIndex) -> None:
        value = self.model.data(index)
        if value is None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Data")
        dialog.resize(640, 360)
        text = QPlainTextEdit(str(value))
        text.setReadOnly(True)
        QVBoxLayout(dialog).addWidget(text)
        dialog.exec()
