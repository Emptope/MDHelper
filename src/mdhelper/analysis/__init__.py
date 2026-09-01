"""Built-in complete analysis pipelines."""

from __future__ import annotations

from mdhelper.plugins.analysis import (
    AnalysisInput,
    AnalysisRegistry,
    BackendAdapter,
)

from .gromacs import GromacsBackend
from .mdanalysis import MDAnalysisBackend
from .native import NativeBackend

DEFAULT_ANALYSIS_REGISTRY = AnalysisRegistry(
    (NativeBackend(), MDAnalysisBackend(), GromacsBackend())
)

__all__ = [
    "DEFAULT_ANALYSIS_REGISTRY",
    "AnalysisInput",
    "AnalysisRegistry",
    "BackendAdapter",
    "GromacsBackend",
    "MDAnalysisBackend",
    "NativeBackend",
]
