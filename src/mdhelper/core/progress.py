"""Shared progress event contract for application and presentation adapters."""

from collections.abc import Callable

ProgressCallback = Callable[[int, int | None, str], None]

__all__ = ["ProgressCallback"]
