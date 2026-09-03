"""Unified external software configuration, detection, status, and execution."""

from mdhelper.core.integrations import (
    Detection,
    IntegrationConfig,
    IntegrationRunRecord,
    IntegrationStatus,
)
from mdhelper.integrations.gromacs import GromacsAdapter
from mdhelper.integrations.registry import IntegrationAdapter, IntegrationRegistry
from mdhelper.integrations.vmd import VmdAdapter

DEFAULT_INTEGRATION_REGISTRY = IntegrationRegistry()
DEFAULT_INTEGRATION_REGISTRY.register(GromacsAdapter())
DEFAULT_INTEGRATION_REGISTRY.register(VmdAdapter())

__all__ = [
    "DEFAULT_INTEGRATION_REGISTRY",
    "Detection",
    "GromacsAdapter",
    "IntegrationAdapter",
    "IntegrationConfig",
    "IntegrationRegistry",
    "IntegrationRunRecord",
    "IntegrationStatus",
    "VmdAdapter",
]
