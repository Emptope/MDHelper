"""Windows console lifecycle support for the frozen launcher."""

from __future__ import annotations

import locale
import os
import sys
from collections.abc import Callable
from typing import Protocol, TextIO, cast

ATTACH_PARENT_PROCESS = -1
STD_INPUT_HANDLE = -10
STD_OUTPUT_HANDLE = -11
STD_ERROR_HANDLE = -12
INVALID_HANDLES = {0, -1, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF}


class StandardHandles(Protocol):
    def GetStdHandle(self, identifier: int) -> int | None: ...


def _standard_handle(kernel: StandardHandles, identifier: int) -> int | None:
    value = kernel.GetStdHandle(identifier)
    if value is None:
        return None
    handle = int(value)
    return None if handle in INVALID_HANDLES else handle


def _open_stream(handle: int, mode: str) -> TextIO:
    import msvcrt

    access = os.O_RDONLY if mode == "r" else os.O_WRONLY
    open_handle = cast(Callable[[int, int], int], vars(msvcrt)["open_osfhandle"])
    binary = cast(int, vars(os)["O_BINARY"])
    descriptor = open_handle(handle, access | binary)
    return cast(
        TextIO,
        open(
            descriptor,
            mode,
            encoding=locale.getencoding(),
            errors="replace",
        ),
    )


def _restore_streams(kernel: StandardHandles) -> None:
    streams: dict[tuple[int, str], TextIO] = {}
    specifications = (
        ("stdin", STD_INPUT_HANDLE, "r"),
        ("stdout", STD_OUTPUT_HANDLE, "w"),
        ("stderr", STD_ERROR_HANDLE, "w"),
    )
    for name, identifier, mode in specifications:
        if getattr(sys, name) is not None:
            continue
        handle = _standard_handle(kernel, identifier)
        if handle is None:
            continue
        key = (handle, mode)
        stream = streams.get(key)
        if stream is None:
            try:
                stream = _open_stream(handle, mode)
            except OSError:
                continue
            streams[key] = stream
        setattr(sys, name, stream)
        setattr(sys, f"__{name}__", stream)


def show() -> None:
    import ctypes

    windll = getattr(ctypes, "windll", None)
    if windll is None:
        return
    kernel = windll.kernel32
    window = kernel.GetConsoleWindow()
    if not window:
        if not kernel.AttachConsole(ATTACH_PARENT_PROCESS) and not kernel.AllocConsole():
            return
        window = kernel.GetConsoleWindow()
    if window:
        windll.user32.ShowWindow(window, 5)
    _restore_streams(kernel)


def detach() -> None:
    import ctypes

    windll = getattr(ctypes, "windll", None)
    if windll is None:
        return
    windll.kernel32.FreeConsole()
