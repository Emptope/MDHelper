"""Windows launch contracts, exercised without a Windows desktop."""

from __future__ import annotations

import subprocess
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

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
    monkeypatch.setattr(gui_main, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(gui_main, "tui_command", lambda: ["mdhelper.exe", "tui"])
    assert gui_main.start_tui()
    assert launch.call_args.args == (["mdhelper.exe", "tui"],)
    assert launch.call_args.kwargs["creationflags"] == NEW_CONSOLE
    assert launch.call_args.kwargs["close_fds"] is True
    launch.side_effect = OSError("launch failed")
    assert not gui_main.start_tui()


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
