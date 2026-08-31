"""Analysis entry points and the narrow algorithm registry."""

from __future__ import annotations

from mdhelper.plugins.analysis import (
    AnalysisBackend,
    AnalysisInput,
    AnalysisRegistry,
    AnalysisRunner,
    FunctionBackend,
)

from .cumulative_rdf import run_cumulative_rdf
from .energy import GmxEnergy, MdaEnergy
from .gmx_rdf import GmxRdf
from .rdf import run_rdf

DEFAULT_ANALYSIS_REGISTRY = AnalysisRegistry()
DEFAULT_ANALYSIS_REGISTRY.register("rdf", FunctionBackend(run_rdf))
DEFAULT_ANALYSIS_REGISTRY.register("rdf", GmxRdf())
DEFAULT_ANALYSIS_REGISTRY.register("cumulative_rdf", FunctionBackend(run_cumulative_rdf))
DEFAULT_ANALYSIS_REGISTRY.register("cumulative_rdf", GmxRdf())
DEFAULT_ANALYSIS_REGISTRY.register("energy", GmxEnergy())
DEFAULT_ANALYSIS_REGISTRY.register("energy", MdaEnergy())

__all__ = [
    "DEFAULT_ANALYSIS_REGISTRY",
    "AnalysisBackend",
    "AnalysisInput",
    "AnalysisRegistry",
    "AnalysisRunner",
    "FunctionBackend",
    "GmxEnergy",
    "GmxRdf",
    "MdaEnergy",
    "run_cumulative_rdf",
    "run_rdf",
]
