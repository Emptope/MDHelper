"""Workspace file view contracts."""

from __future__ import annotations

from dataclasses import dataclass

DATA_COLUMNS = ("Data", "Index", "Value")


@dataclass(frozen=True)
class DataLayout:
    columns: tuple[str, ...] = DATA_COLUMNS
    selectable: tuple[int, ...] = ()
    streaming: bool = False


@dataclass(frozen=True)
class ImageInfo:
    width: int
    height: int
    format: str


@dataclass(frozen=True)
class ImagePixels:
    width: int
    height: int
    rgba: bytes


@dataclass(frozen=True)
class WorkspaceFile:
    path: str
    text: str
    editable: bool
    parsed: bool
    message: str
    layout: DataLayout = DataLayout()
    image: ImageInfo | None = None


@dataclass(frozen=True)
class DataSection:
    name: str
    columns: tuple[str, ...]
    rows: int


@dataclass(frozen=True)
class DataPage:
    section: DataSection
    offset: int
    rows: tuple[tuple[str, ...], ...]
    complete: bool = True


__all__ = ["DataLayout", "DataPage", "DataSection", "ImageInfo", "ImagePixels", "WorkspaceFile"]
