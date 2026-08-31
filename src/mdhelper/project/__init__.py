"""Versioned project persistence boundary."""

from .project import Project
from .schema import PROJECT_SCHEMA_VERSION

__all__ = ["PROJECT_SCHEMA_VERSION", "Project"]
