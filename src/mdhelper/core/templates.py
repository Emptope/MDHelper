"""Backend-neutral contracts for bundled text templates."""

from __future__ import annotations

from dataclasses import dataclass

from .errors import ConfigurationError


@dataclass(frozen=True)
class TextTemplate:
    key: str
    title: str
    category: str
    filename: str
    content: str

    def to_dict(self, include_content: bool = False) -> dict[str, str]:
        value = {
            "key": self.key,
            "title": self.title,
            "category": self.category,
            "filename": self.filename,
        }
        if include_content:
            value["content"] = self.content
        return value


class TemplateRegistry:
    """Register text templates by stable, case-insensitive keys."""

    def __init__(self) -> None:
        self._templates: dict[str, TextTemplate] = {}

    def register(self, template: TextTemplate) -> None:
        key = template.key.strip().casefold()
        if not key:
            raise ConfigurationError("A template must have a non-empty key.")
        if key in self._templates:
            raise ConfigurationError(f"A template is already registered: {key}")
        if not template.content:
            raise ConfigurationError(f"Template {key!r} is empty.")
        if not template.content.isascii():
            raise ConfigurationError(f"Template {key!r} must contain ASCII text only.")
        self._templates[key] = template

    def get(self, key: str) -> TextTemplate:
        try:
            return self._templates[key.casefold()]
        except KeyError as exc:
            raise ConfigurationError(f"Unknown template: {key!r}") from exc

    def templates(self) -> tuple[TextTemplate, ...]:
        return tuple(
            sorted(
                self._templates.values(),
                key=lambda item: (item.category.casefold(), item.title.casefold()),
            )
        )
