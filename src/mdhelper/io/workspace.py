"""Temporary disk-backed storage for sequential file data."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from tempfile import TemporaryDirectory

from mdhelper.core.workspace import DATA_COLUMNS, DataPage, DataSection


class DataStore:
    def __init__(self, columns: tuple[str, ...] = DATA_COLUMNS) -> None:
        self.columns = columns
        self._directory = TemporaryDirectory(prefix="mdhelper-data-")
        self.path = Path(self._directory.name) / "rows.sqlite"
        self._connection = sqlite3.connect(self.path)
        self._connection.execute("CREATE TABLE rows (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        self.count = 0

    def append(self, rows: Iterable[tuple[str, ...]]) -> None:
        records = []
        for row in rows:
            records.append((self.count, json.dumps(row, ensure_ascii=True)))
            self.count += 1
        self._connection.executemany("INSERT INTO rows VALUES (?, ?)", records)

    def finish(self) -> None:
        self._connection.commit()

    def page(self, offset: int, limit: int) -> DataPage:
        if offset < 0 or limit < 1:
            raise ValueError("Invalid data page range")
        cursor = self._connection.execute(
            "SELECT value FROM rows WHERE id >= ? AND id < ? ORDER BY id",
            (offset, offset + limit),
        )
        return DataPage(
            DataSection("Data", self.columns, self.count), offset,
            tuple(tuple(json.loads(row[0])) for row in cursor),
        )

    def close(self) -> None:
        self._connection.close()
        self._directory.cleanup()
