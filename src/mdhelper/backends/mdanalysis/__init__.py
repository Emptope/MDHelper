"""MDAnalysis input adapters."""

from .selection import (
    SELECTION_LANGUAGE,
    SELECTION_LANGUAGE_VERSION,
    MDAnalysisSelectionEngine,
)
from .trajectory import MDAnalysisTrajectorySource

__all__ = [
    "SELECTION_LANGUAGE",
    "SELECTION_LANGUAGE_VERSION",
    "MDAnalysisSelectionEngine",
    "MDAnalysisTrajectorySource",
]
