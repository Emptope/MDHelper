"""Native checks for desktop startup and the packaged terminal entry."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path


def console_probe(pid: int) -> int:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.FreeConsole()
    attached = bool(kernel.AttachConsole(pid))
    error = ctypes.get_last_error()
    if attached:
        kernel.FreeConsole()
        return 0
    if error not in (6, 87):
        raise OSError(error, "Could not determine launcher console ownership")
    return 10


def has_console(pid: int) -> bool:
    result = subprocess.run(
        [sys.executable, __file__, "--console-pid", str(pid)],
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
        timeout=15,
    )
    if result.returncode not in (0, 10):
        raise RuntimeError(result.stderr.decode(errors="replace"))
    return result.returncode == 0


def process_tree(pid: int) -> set[int]:
    class Entry(ctypes.Structure):
        _fields_ = [
            ("size", wintypes.DWORD), ("usage", wintypes.DWORD),
            ("pid", wintypes.DWORD), ("heap", ctypes.c_size_t),
            ("module", wintypes.DWORD), ("threads", wintypes.DWORD),
            ("parent", wintypes.DWORD), ("priority", wintypes.LONG),
            ("flags", wintypes.DWORD), ("name", wintypes.WCHAR * 260),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    parents = {}
    names = {}
    try:
        entry = Entry()
        entry.size = ctypes.sizeof(entry)
        found = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while found:
            parents[entry.pid] = entry.parent
            names[entry.pid] = entry.name
            found = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    result = {pid}
    while True:
        children = {child for child, parent in parents.items() if parent in result}
        if children <= result:
            return {child for child in result if names.get(child) == names.get(pid)}
        result |= children


def visible_windows(pids: set[int]) -> list[int]:
    user = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    windows: list[int] = []

    @callback_type
    def visit(handle: int, _data: int) -> bool:
        owner = wintypes.DWORD()
        user.GetWindowThreadProcessId(handle, ctypes.byref(owner))
        if owner.value in pids and user.IsWindowVisible(handle):
            windows.append(handle)
        return True

    if not user.EnumWindows(visit, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    return windows


def close_gui(process: subprocess.Popen[bytes], windows: list[int]) -> None:
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user.GetLastActivePopup.argtypes = [wintypes.HWND]
    user.GetLastActivePopup.restype = wintypes.HWND
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    for window in windows:
        user.PostMessageW(window, 0x0010, 0, 0)
    deadline = time.monotonic() + 15
    while process.poll() is None:
        if time.monotonic() >= deadline:
            raise TimeoutError("GUI did not close after confirmation")
        for window in windows:
            popup = user.GetLastActivePopup(window)
            if popup and popup != window and user.IsWindowVisible(popup):
                user.PostMessageW(popup, 0x0100, 0x0D, 0)
                user.PostMessageW(popup, 0x0101, 0x0D, 0)
        time.sleep(0.1)
    if process.returncode != 0:
        raise RuntimeError(f"GUI shutdown failed: {process.returncode}")


def check_gui(application: Path, arguments: list[str]) -> None:
    environment = dict(os.environ)
    environment.pop("QT_QPA_PLATFORM", None)
    with subprocess.Popen(
        [str(application), *arguments],
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    ) as process:
        try:
            deadline = time.monotonic() + 60
            while True:
                if process.poll() is not None:
                    raise RuntimeError(
                        f"Desktop launcher exited before opening a window: {process.returncode}"
                    )
                pids = process_tree(process.pid)
                if any(has_console(pid) for pid in pids):
                    raise RuntimeError("GUI launcher allocated a console")
                windows = visible_windows(pids)
                if windows:
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError("Desktop launcher did not open a visible window")
                time.sleep(0.1)
            time.sleep(2)
            if process.poll() is not None or any(
                has_console(pid) for pid in process_tree(process.pid)
            ):
                raise RuntimeError("GUI did not remain running without a console")
            close_gui(process, windows)
        finally:
            if process.poll() is None:
                # Stop children first so the outer launcher can clean its temporary files.
                children = process_tree(process.pid) - {process.pid}
                for pid in children or {process.pid}:
                    subprocess.run(
                        ["taskkill.exe", "/PID", str(pid), "/T", "/F"],
                        capture_output=True,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                        timeout=15,
                        check=False,
                    )
            process.communicate(timeout=15)
    print(f"Verified native GUI startup without a console: {arguments}")


def check_terminal(application: Path) -> None:
    with subprocess.Popen(
        [str(application)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
        text=True,
    ) as process:
        try:
            deadline = time.monotonic() + 60
            while not has_console(process.pid):
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("Terminal launcher did not receive a console")
                time.sleep(0.1)
            output, error = process.communicate("q\n", timeout=60)
            if process.returncode != 0 or not output:
                raise RuntimeError(f"Terminal input/output check failed: {error}")
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=15)
    print("Verified terminal allocation, input, output, and exit status")


def check_forwarder(application: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="mdhelper launch ") as temporary:
        root = Path(temporary)
        copied = root / "application with spaces.exe"
        terminal = copied.with_suffix(".com")
        shutil.copy2(application, copied)
        shutil.copy2(application.with_suffix(".com"), terminal)
        config = root / "settings with spaces.toml"
        config.write_text("", encoding="ascii")
        report = root / "redirected output.json"
        environment = dict(os.environ)
        environment.update({
            "_PYI_ARCHIVE_FILE": str(copied),
            "_PYI_PARENT_PROCESS_LEVEL": "1",
            "_PYI_APPLICATION_HOME_DIR": str(root / "expired runtime"),
            "PYINSTALLER_RESET_ENVIRONMENT": "0",
        })
        with report.open("wb") as output:
            result = subprocess.run(
                [str(terminal), "cli", "--settings", str(config), "config", "check"],
                stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW, timeout=60, env=environment,
            )
        if result.returncode != 0:
            raise RuntimeError(f"Forwarded CLI command failed: {result.stderr!r}")
        data = json.loads(report.read_bytes())
        if Path(data["path"]).resolve() != config.resolve() or data["exists"] is not True:
            raise RuntimeError("Forwarder did not preserve quoted arguments and file redirection")
        result = subprocess.run(
            [str(terminal), "cli", "--invalid-option"], capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW, timeout=60,
        )
        if result.returncode != 2 or not result.stderr:
            raise RuntimeError("Forwarder did not preserve the CLI error status and stderr")
        copied.unlink()
        result = subprocess.run(
            [str(terminal)], capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW, timeout=15,
        )
        if result.returncode == 0 or not result.stderr:
            raise RuntimeError("Forwarder did not report the missing application")
    print("Verified independent runtime, quoted paths, redirection, and failure handling")


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--application", type=Path)
    mode.add_argument("--console-pid", type=int)
    args = parser.parse_args()
    if args.console_pid is not None:
        return console_probe(args.console_pid)
    application = args.application.resolve()
    for arguments in ([], ["gui"]):
        check_gui(application, arguments)
    check_terminal(application.with_suffix(".com"))
    check_forwarder(application)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
