"""Bundled text-template feature."""

from __future__ import annotations

from pathlib import Path

from mdhelper.core.templates import TemplateRegistry, TextTemplate
from mdhelper.services.templates import load_templates, write_template


class TemplateFeature:
    def __init__(self, registry: TemplateRegistry | None = None):
        self.registry = load_templates() if registry is None else registry

    def list(self) -> tuple[TextTemplate, ...]:
        return self.registry.templates()

    def get(self, key: str) -> TextTemplate:
        return self.registry.get(key)

    def save(self, key: str, destination: str | Path) -> Path:
        return write_template(self.get(key), destination)
