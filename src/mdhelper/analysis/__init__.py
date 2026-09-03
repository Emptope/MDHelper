"""Built-in complete analysis pipelines."""

from __future__ import annotations

from mdhelper.analysis.pipeline import (
    AnalysisInput,
    AnalysisRegistry,
    BackendAdapter,
)

from .gromacs import GromacsBackend
from .mdanalysis import MDAnalysisBackend

DEFAULT_ANALYSIS_REGISTRY = AnalysisRegistry(
    (MDAnalysisBackend(), GromacsBackend())
)

__all__ = [
    "DEFAULT_ANALYSIS_REGISTRY",
    "AnalysisInput",
    "AnalysisRegistry",
    "BackendAdapter",
    "GromacsBackend",
    "MDAnalysisBackend",
]
