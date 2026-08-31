"""Backend-independent static atom-selection port."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from .system import Atom


class SelectionEngine(Protocol):
    language: str
    language_version: str

    def resolve_many(
        self, atoms: Sequence[Atom], expressions: Sequence[str]
    ) -> tuple[tuple[int, ...], ...]: ...
