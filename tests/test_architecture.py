from __future__ import annotations

import ast
from pathlib import Path


def test_package_dependency_boundaries() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "mdhelper"
    presentation = {"cli", "gui", "tui"}
    for path in root.rglob("*.py"):
        owner = path.relative_to(root).parts[0]
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                modules = [node.module or ""]
            for module in modules:
                if module.startswith("PySide6"):
                    assert owner == "gui", (path, module)
                if not module.startswith("mdhelper."):
                    continue
                target = module.split(".")[1]
                if owner == "core":
                    assert target == "core", (path, module)
                if target in presentation and target != owner:
                    assert owner == "bootstrap", (path, module)
                if owner in presentation:
                    assert target not in {"analysis", "backends"}, (path, module)
                if owner in {"analysis", "backends", "integrations", "runtime", "io"}:
                    assert target not in presentation | {"app"}, (path, module)
                if owner in {"analysis", "backends"}:
                    assert not module.startswith("mdhelper.core.plotting"), (path, module)
