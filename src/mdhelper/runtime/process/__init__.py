"""External-process runtime API."""

from .contracts import ExecutionAdapter, ExecutionStatus
from .lifecycle import ProcessProgress, hidden_window_flags, run_integration
from .records import format_command
from .terminal import launch_in_terminal, terminal_command

__all__ = [
    "ExecutionAdapter",
    "ExecutionStatus",
    "ProcessProgress",
    "format_command",
    "hidden_window_flags",
    "launch_in_terminal",
    "run_integration",
    "terminal_command",
]
