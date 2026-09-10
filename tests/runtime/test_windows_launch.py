"""Windows launch contracts, exercised without a Windows desktop."""

from __future__ import annotations

import subprocess
from importlib import import_module
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import mdhelper.bootstrap.windows_console as console
import mdhelper.runtime.detection as detection
import mdhelper.runtime.process.lifecycle as lifecycle
import mdhelper.runtime.process.terminal as terminal

gui_main = import_module("mdhelper.gui.main")

NO_WINDOW = 0x08000000
NEW_GROUP = 0x00000200
NEW_CONSOLE = 0x00000010


@pytest.fixture
def windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lifecycle, "os", SimpleNamespace(name="nt"))
    for name, value in (
        ("CREATE_NO_WINDOW", NO_WINDOW),
        ("CREATE_NEW_PROCESS_GROUP", NEW_GROUP),
        ("CREATE_NEW_CONSOLE", NEW_CONSOLE),
    ):
        monkeypatch.setattr(subprocess, name, value, raising=False)


def test_detection_has_no_console(windows: None, monkeypatch: pytest.MonkeyPatch) -> None:
    run = Mock(return_value=subprocess.CompletedProcess([], 0))
    monkeypatch.setattr(subprocess, "run", run)
    detection._run("gmx.exe", (), ("--version",), 10, {})
    assert run.call_args.args == (["gmx.exe", "--version"],)
    assert run.call_args.kwargs["creationflags"] == NO_WINDOW
    assert run.call_args.kwargs["capture_output"] is True
    assert run.call_args.kwargs["shell"] is False


@pytest.mark.parametrize("input_text", [None, "0\n"])
def test_background_analysis_has_no_console(
    windows: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, input_text: str | None,
) -> None:
    launch = Mock()
    monkeypatch.setattr(subprocess, "Popen", launch)
    lifecycle._start(Mock(), ["gmx.exe", "energy"], tmp_path, {}, input_text)
    options = launch.call_args.kwargs
    assert options["creationflags"] == NO_WINDOW | NEW_GROUP
    assert options["start_new_session"] is False
    assert options["shell"] is False
    assert options["stdin"] == (subprocess.PIPE if input_text is not None else subprocess.DEVNULL)
    assert options["stdout"] == subprocess.PIPE
    assert options["stderr"] == subprocess.PIPE


def test_background_cancellation_has_no_console(
    windows: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = Mock()
    monkeypatch.setattr(subprocess, "run", run)
    process = Mock(pid=123)
    lifecycle._signal_tree(process, force=True)
    assert run.call_args.args == (["taskkill", "/PID", "123", "/T", "/F"],)
    assert run.call_args.kwargs["creationflags"] == NO_WINDOW
    assert run.call_args.kwargs["capture_output"] is True


def test_gui_tui_launch_requests_an_interactive_console(
    windows: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    launch = Mock()
    monkeypatch.setattr(subprocess, "Popen", launch)
    monkeypatch.setattr(
        gui_main, "sys",
        SimpleNamespace(platform="win32", executable="mdhelper.exe", frozen=True),
    )
    assert gui_main.start_tui()
    assert launch.call_args.args == (["mdhelper.com", "tui"],)
    assert launch.call_args.kwargs["creationflags"] == NEW_CONSOLE
    assert launch.call_args.kwargs["close_fds"] is True
    launch.side_effect = OSError("launch failed")
    assert not gui_main.start_tui()


@pytest.mark.parametrize("parent", ["1729", "invalid", "-2", "4294967296"])
def test_console_attaches_to_forwarder_without_losing_redirects(
    monkeypatch: pytest.MonkeyPatch, parent: str,
) -> None:
    handles = {-10: 101, -11: 102, -12: 103}
    kernel = Mock()
    kernel.GetConsoleWindow.side_effect = [0, 50]
    kernel.GetStdHandle.side_effect = handles.__getitem__
    kernel.GetFileType.side_effect = lambda handle: {101: 2, 102: 1, 103: 3}[handle]

    def attach(pid: int) -> bool:
        handles.update({-10: 201, -11: 202, -12: 203})
        return True

    kernel.AttachConsole.side_effect = attach
    opened: list[tuple[int, str]] = []

    def stream(handle: int, mode: str) -> StringIO:
        opened.append((handle, mode))
        return StringIO()

    with monkeypatch.context() as patch:
        patch.setenv("MDHELPER_CONSOLE_PID", parent)
        patch.setattr(console, "_api", lambda: SimpleNamespace(kernel32=kernel, user32=Mock()))
        patch.setattr(console, "_open_stream", stream)
        patch.setattr(console, "sys", SimpleNamespace(stdin=None, stdout=None, stderr=None))
        console.show()
        assert "MDHELPER_CONSOLE_PID" not in console.os.environ
    kernel.AttachConsole.assert_called_once_with(1729 if parent == "1729" else -1)
    kernel.AllocConsole.assert_not_called()
    assert opened == [(102, "w"), (103, "w"), (201, "r")]


def test_windowed_gui_rejects_invalid_arguments_without_stderr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gui_main, "sys", SimpleNamespace(stderr=None))
    assert gui_main.main(["--invalid-option"]) == 2


def test_interactive_tool_launch_requests_a_console(
    windows: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    launch = Mock()
    monkeypatch.setattr(subprocess, "Popen", launch)
    monkeypatch.setattr(terminal.sys, "platform", "win32")
    monkeypatch.setattr(terminal, "record_command", Mock())
    adapter = Mock()
    adapter.name = "gromacs"
    adapter.command_prefix.return_value = ()
    adapter.environment_keys.return_value = frozenset()
    status = Mock(available=True, path="gmx.exe", version="2025")
    status.name = "gromacs"
    terminal.launch_in_terminal(
        adapter, status, ["make_ndx", "-f", "input with spaces.gro"], tmp_path,
        environment={},
    )
    assert launch.call_args.args == (["gmx.exe", "make_ndx", "-f", "input with spaces.gro"],)
    assert launch.call_args.kwargs["creationflags"] == NEW_CONSOLE
    assert launch.call_args.kwargs["shell"] is False
