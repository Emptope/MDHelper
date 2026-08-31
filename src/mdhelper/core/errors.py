"""Stable, actionable domain error taxonomy shared by every adapter."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MDHelperError(Exception):
    message: str
    hint: str = ""
    code: str = "mdhelper_error"
    exit_code: int = 10
    details: dict[str, object] | None = None

    def __str__(self) -> str:
        return self.message

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "error": self.code,
            "message": self.message,
            "hint": self.hint,
        }
        if self.details:
            value["details"] = self.details
        return value


class ConfigurationError(MDHelperError):
    def __init__(self, message: str, hint: str = "", details: dict[str, object] | None = None):
        super().__init__(message, hint, "configuration_error", 3, details)


class InputFileError(MDHelperError):
    def __init__(self, message: str, hint: str = "", details: dict[str, object] | None = None):
        super().__init__(message, hint, "input_file_error", 4, details)


class FormatError(MDHelperError):
    def __init__(self, message: str, hint: str = "", details: dict[str, object] | None = None):
        super().__init__(message, hint, "format_error", 4, details)


class TopologyError(MDHelperError):
    def __init__(self, message: str, hint: str = "", details: dict[str, object] | None = None):
        super().__init__(message, hint, "topology_error", 4, details)


class TrajectoryError(MDHelperError):
    def __init__(self, message: str, hint: str = "", details: dict[str, object] | None = None):
        super().__init__(message, hint, "trajectory_error", 4, details)


class SelectionError(MDHelperError):
    def __init__(self, message: str, hint: str = "", details: dict[str, object] | None = None):
        super().__init__(message, hint, "selection_error", 5, details)


class InputError(MDHelperError):
    def __init__(self, message: str, hint: str = "", details: dict[str, object] | None = None):
        super().__init__(message, hint, "input_error", 5, details)


class BackendError(MDHelperError):
    def __init__(self, message: str, hint: str = "", details: dict[str, object] | None = None):
        super().__init__(message, hint, "backend_error", 6, details)


class TaskCancelled(MDHelperError):
    def __init__(
        self,
        message: str = "Analysis was cancelled.",
        details: dict[str, object] | None = None,
    ):
        super().__init__(
            message,
            "Incomplete results were not committed.",
            "task_cancelled",
            7,
            details,
        )
