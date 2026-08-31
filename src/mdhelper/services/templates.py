"""Discovery of independently stored bundled text templates."""

from __future__ import annotations

import os
from pathlib import Path

from mdhelper.core.errors import ConfigurationError
from mdhelper.core.templates import TemplateRegistry, TextTemplate

TEMPLATE_ROOT = Path(__file__).parents[1] / "resources" / "templates"


def load_templates(root: str | Path = TEMPLATE_ROOT) -> TemplateRegistry:
    """Register every non-hidden text file below a template root."""

    directory = Path(root)
    registry = TemplateRegistry()
    if not directory.is_dir():
        raise ConfigurationError(f"Template directory is unavailable: {directory}")
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        relative = path.relative_to(directory)
        if any(part.startswith(".") for part in relative.parts):
            continue
        try:
            content = path.read_text(encoding="ascii")
        except (OSError, UnicodeDecodeError) as exc:
            raise ConfigurationError(
                f"Could not load ASCII template: {relative.as_posix()}",
                details={"exception": f"{type(exc).__name__}: {exc}"},
            ) from exc
        category = relative.parts[0] if len(relative.parts) > 1 else "general"
        key = relative.with_suffix("").as_posix()
        title = relative.stem.replace("_", " ").replace("-", " ").title()
        registry.register(
            TextTemplate(key, title, category.title(), relative.name, content)
        )
    return registry


def write_template(template: TextTemplate, destination: str | Path) -> Path:
    path = Path(destination).expanduser().resolve()
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(template.content, encoding="ascii")
        os.replace(temporary, path)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise ConfigurationError(
            f"Could not save template: {path}",
            details={"exception": f"{type(exc).__name__}: {exc}"},
        ) from exc
    return path
