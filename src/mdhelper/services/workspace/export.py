"""Export parsed Workspace records as UTF-8 CSV or tab-delimited TXT."""

from __future__ import annotations

import csv
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Event

from mdhelper.core.errors import ConfigurationError

from .document import WorkspaceDocument
from .text import check_cancel


def export_workspace_data(
    source: str | Path, destination: str | Path, cancel: Event | None = None,
    columns: tuple[int, ...] | None = None,
) -> Path:
    source = Path(source).expanduser().resolve()
    target = Path(destination).expanduser().resolve()
    if source == target or (target.exists() and target.samefile(source)):
        raise ConfigurationError("Cannot overwrite the source file with exported data")
    suffix = Path(destination).suffix.lower()
    if suffix not in (".csv", ".txt"):
        raise ConfigurationError("Export format must be CSV (.csv) or text (.txt)")
    delimiter = "," if suffix == ".csv" else "\t"
    temporary: Path | None = None
    try:
        with WorkspaceDocument(source, cancel) as document:
            if not document.file.parsed:
                raise ConfigurationError("This file has no parsed data to export")
            layout = document.file.layout
            selected = tuple(range(len(layout.columns))) if columns is None else columns
            if not selected or len(set(selected)) != len(selected) or any(
                not isinstance(column, int) or not 0 <= column < len(layout.columns)
                for column in selected
            ):
                raise ConfigurationError("Invalid export columns")
            if layout.selectable and not set(selected).intersection(layout.selectable):
                raise ConfigurationError("Select at least one term to export")
            with NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="", dir=target.parent,
                prefix=f".{target.name}.", suffix=".tmp", delete=False,
            ) as handle:
                temporary = Path(handle.name)
                writer = csv.writer(handle, delimiter=delimiter, lineterminator="\n")
                writer.writerow(layout.columns[column] for column in selected)
                offset = 0
                while True:
                    check_cancel(cancel)
                    page = document.page(offset)
                    writer.writerows(tuple(row[column] for column in selected) for row in page.rows)
                    offset += len(page.rows)
                    if page.complete:
                        break
                handle.flush()
                os.fsync(handle.fileno())
        check_cancel(cancel)
        os.replace(temporary, target)
        return target
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
