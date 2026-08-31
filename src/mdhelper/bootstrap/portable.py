"""Unified interface dispatch and portable configuration bootstrap."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, MutableMapping
from importlib.util import find_spec
from pathlib import Path

PORTABLE_CONFIG = "config.toml"
GUI_UNAVAILABLE = 6
GUI_PROCESS = "MDHELPER_GUI_PROCESS"
RESET_FROZEN_ENV = "PYINSTALLER_RESET_ENVIRONMENT"
DETACHED_PROCESS = 0x00000008


def portable_config_path(
    executable: str | Path | None = None,
    frozen: bool | None = None,
) -> Path | None:
    """Return the colocated config for every frozen distribution."""

    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if not is_frozen:
        return None
    program = Path(sys.executable if executable is None else executable).resolve()
    return program.parent / PORTABLE_CONFIG


def activate_portable_config(
    environment: MutableMapping[str, str] | None = None,
    executable: str | Path | None = None,
    frozen: bool | None = None,
) -> Path | None:
    """Select the colocated config unless the caller already supplied an override."""

    env = os.environ if environment is None else environment
    path = portable_config_path(executable, frozen)
    if path is not None and not env.get("MDHELPER_CONFIG"):
        env["MDHELPER_CONFIG"] = str(path)
    return path


def cli_main(argv: list[str] | None = None) -> int:
    activate_portable_config()
    from mdhelper.cli.main import main

    return main(argv)


def tui_main(argv: list[str] | None = None) -> int:
    activate_portable_config()
    from mdhelper.tui.main import main

    return main(argv)


def gui_main(argv: list[str] | None = None) -> int:
    activate_portable_config()
    from mdhelper.gui.main import main

    return main(argv)


def gui_available(
    environment: MutableMapping[str, str] | None = None,
    platform: str | None = None,
    module_finder: Callable[[str], object | None] = find_spec,
) -> bool:
    """Return whether Qt and a usable display are available for GUI startup."""

    env = os.environ if environment is None else environment
    system = sys.platform if platform is None else platform
    if module_finder("PySide6") is None:
        return False
    if system.startswith("linux"):
        return bool(
            env.get("DISPLAY")
            or env.get("WAYLAND_DISPLAY")
            or env.get("QT_QPA_PLATFORM")
        )
    return True


def show_console(
    platform: str | None = None,
    frozen: bool | None = None,
) -> None:
    """Reveal the packaged Windows console only for terminal interfaces."""

    system = sys.platform if platform is None else platform
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if system != "win32" or not is_frozen:
        return
    from mdhelper.bootstrap.windows_console import show

    show()


def detach_console(
    platform: str | None = None,
    frozen: bool | None = None,
) -> None:
    """Detach the packaged Windows console before GUI startup."""

    system = sys.platform if platform is None else platform
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if system != "win32" or not is_frozen:
        return
    from mdhelper.bootstrap.windows_console import detach

    detach()


def start_gui(
    argv: list[str],
    environment: MutableMapping[str, str] | None = None,
    platform: str | None = None,
    frozen: bool | None = None,
    executable: str | Path | None = None,
) -> int:
    """Start a packaged GUI independently from its console launcher."""

    env = os.environ if environment is None else environment
    system = sys.platform if platform is None else platform
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    is_gui_process = env.get(GUI_PROCESS) == "1"
    if system == "win32" and is_frozen and not is_gui_process:
        program = str(sys.executable if executable is None else executable)
        child_env = dict(env)
        child_env[GUI_PROCESS] = "1"
        child_env[RESET_FROZEN_ENV] = "1"
        try:
            subprocess.Popen(
                [program, "gui", *argv],
                close_fds=True,
                creationflags=DETACHED_PROCESS,
                env=child_env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            return GUI_UNAVAILABLE
        return 0
    if is_gui_process:
        env.pop(GUI_PROCESS, None)
        env.pop(RESET_FROZEN_ENV, None)
    detach_console(system, is_frozen)
    return gui_main(argv)


def main(argv: list[str] | None = None) -> int:
    """Dispatch one public entry point while keeping adapters independent."""

    values = list(sys.argv[1:] if argv is None else argv)
    if not values:
        if gui_available():
            result = start_gui([])
            if result != GUI_UNAVAILABLE:
                return result
        show_console()
        return tui_main([])
    mode, *arguments = values
    if mode == "gui":
        return start_gui(arguments)
    if mode == "tui":
        show_console()
        return tui_main(arguments)
    if mode == "cli":
        show_console()
        return cli_main(arguments)
    show_console()
    return cli_main(values)
