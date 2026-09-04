"""MDAnalysis input adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .selection import (
    SELECTION_LANGUAGE,
    SELECTION_LANGUAGE_VERSION,
    MDAnalysisSelectionEngine,
)

if TYPE_CHECKING:
    from .trajectory import MDAnalysisTrajectorySource


def __getattr__(name: str) -> object:
    if name != "MDAnalysisTrajectorySource":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from .trajectory import MDAnalysisTrajectorySource

    globals()[name] = MDAnalysisTrajectorySource
    return MDAnalysisTrajectorySource

__all__ = [
    "SELECTION_LANGUAGE",
    "SELECTION_LANGUAGE_VERSION",
    "MDAnalysisSelectionEngine",
    "MDAnalysisTrajectorySource",
]
