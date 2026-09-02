from __future__ import annotations

import ast
import re
from functools import cache
from pathlib import Path

ROOT = Path(__file__).parents[1]
SOURCE_ROOT = Path(__file__).parents[1] / "src" / "mdhelper"
PRESENTATION_PACKAGES = ("cli", "gui", "tui")
PRESENTATION_PREFIXES = tuple(f"mdhelper.{name}" for name in PRESENTATION_PACKAGES)
ENGINE_PREFIXES = ("mdhelper.analysis", "mdhelper.backends")
ROOT_MODULES = {"__init__.py", "__main__.py", "version.py"}
GUI_ROOT_MODULES = {
    "__init__.py",
    "fonts.py",
    "formatting.py",
    "main.py",
    "menu.py",
    "theme.py",
    "window.py",
}
GUI_SUBPACKAGES = {"components", "controllers", "dialogs", "pages"}
TUI_ROOT_MODULES = {
    "__init__.py",
    "__main__.py",
    "controller.py",
    "formatting.py",
    "main.py",
    "model.py",
    "terminal.py",
}
TUI_SUBPACKAGES = {"controllers"}
JOB_MODULES = {"__init__.py", "models.py", "runner.py"}
GUI_FORBIDDEN_IMPORTS = {
    "components": ("controllers", "dialogs", "pages"),
    "controllers": ("components", "dialogs", "pages"),
    "dialogs": ("controllers", "pages"),
    "pages": ("controllers",),
}
CODE_SUFFIXES = {".py", ".pyi", ".ps1", ".sh", ".spec", ".toml", ".yaml", ".yml"}


def _module(path: Path) -> str:
    relative = path.relative_to(SOURCE_ROOT.parent).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


@cache
def _imports(path: Path) -> tuple[str, ...]:
    package = _module(path)
    if path.name != "__init__.py":
        package = package.rpartition(".")[0]
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                parts = package.split(".")
                parent = parts[: len(parts) - node.level + 1]
                module = ".".join([*parent, *module.split(".")]).rstrip(".")
            if module:
                imports.append(module)
    return tuple(imports)


@cache
def _files(package: str) -> tuple[Path, ...]:
    return tuple((SOURCE_ROOT / package).rglob("*.py"))


def test_core_has_no_reverse_internal_dependencies() -> None:
    violations = {
        str(path.relative_to(SOURCE_ROOT)): imported
        for path in _files("core")
        for imported in _imports(path)
        if imported.startswith("mdhelper.") and not imported.startswith("mdhelper.core")
    }
    assert violations == {}


def test_presentations_do_not_import_engine_packages() -> None:
    violations = {
        str(path.relative_to(SOURCE_ROOT)): imported
        for package in PRESENTATION_PACKAGES
        for path in _files(package)
        for imported in _imports(path)
        if imported.startswith(ENGINE_PREFIXES)
    }
    assert violations == {}


def test_presentations_do_not_depend_on_each_other() -> None:
    violations = {
        str(path.relative_to(SOURCE_ROOT)): imported
        for package in PRESENTATION_PACKAGES
        for path in _files(package)
        for imported in _imports(path)
        if any(
            imported.startswith(f"mdhelper.{other}")
            for other in PRESENTATION_PACKAGES
            if other != package
        )
    }
    assert violations == {}


def test_only_bootstrap_composes_presentation_packages() -> None:
    violations = {
        str(path.relative_to(SOURCE_ROOT)): imported
        for path in SOURCE_ROOT.rglob("*.py")
        if path.relative_to(SOURCE_ROOT).parts[0]
        not in (*PRESENTATION_PACKAGES, "bootstrap")
        for imported in _imports(path)
        if imported.startswith(PRESENTATION_PREFIXES)
    }
    assert violations == {}


def test_qt_is_confined_to_the_gui_package() -> None:
    violations = {
        str(path.relative_to(SOURCE_ROOT)): imported
        for path in SOURCE_ROOT.rglob("*.py")
        if path.relative_to(SOURCE_ROOT).parts[0] != "gui"
        for imported in _imports(path)
        if imported == "PySide6" or imported.startswith("PySide6.")
    }
    assert violations == {}


def test_package_root_contains_only_entrypoints_and_version() -> None:
    actual = {path.name for path in SOURCE_ROOT.glob("*.py")}
    assert actual == ROOT_MODULES


def test_gui_modules_follow_the_presentation_package_layout() -> None:
    root = SOURCE_ROOT / "gui"
    assert {path.name for path in root.glob("*.py")} == GUI_ROOT_MODULES
    packages = {
        path.name
        for path in root.iterdir()
        if path.is_dir() and (path / "__init__.py").is_file()
    }
    assert packages == GUI_SUBPACKAGES


def test_gui_subpackages_follow_their_dependency_direction() -> None:
    violations = {
        str(path.relative_to(SOURCE_ROOT)): imported
        for package, forbidden in GUI_FORBIDDEN_IMPORTS.items()
        for path in _files(f"gui/{package}")
        for imported in _imports(path)
        if any(imported.startswith(f"mdhelper.gui.{name}") for name in forbidden)
    }
    assert violations == {}


def test_tui_modules_follow_the_presentation_package_layout() -> None:
    root = SOURCE_ROOT / "tui"
    assert {path.name for path in root.glob("*.py")} == TUI_ROOT_MODULES
    packages = {
        path.name
        for path in root.iterdir()
        if path.is_dir() and (path / "__init__.py").is_file()
    }
    assert packages == TUI_SUBPACKAGES


def test_job_execution_and_workflow_packages_are_separate() -> None:
    jobs = SOURCE_ROOT / "jobs"
    workflow = SOURCE_ROOT / "workflow"

    assert {path.name for path in jobs.glob("*.py")} == JOB_MODULES
    assert {path.name for path in workflow.glob("*.py")} == {"__init__.py"}
    assert _imports(workflow / "__init__.py") == ()


def test_source_uses_detection_terminology() -> None:
    term = "pro" + "be"
    pattern = re.compile(rf"\b{term}s?\b", re.IGNORECASE)
    violations = {
        str(path.relative_to(SOURCE_ROOT))
        for path in SOURCE_ROOT.rglob("*.py")
        if pattern.search(path.read_text(encoding="utf-8"))
    }
    assert violations == set()


def test_source_and_automation_files_are_ascii() -> None:
    roots = (ROOT / "src", ROOT / "tests", ROOT / "packaging", ROOT / ".github")
    files = (
        path
        for root in roots
        for path in root.rglob("*")
        if path.is_file() and path.suffix in CODE_SUFFIXES
    )
    violations = []
    for path in files:
        try:
            path.read_text(encoding="ascii")
        except UnicodeDecodeError:
            violations.append(str(path.relative_to(ROOT)))
    assert violations == []


def test_runtime_does_not_import_integrations() -> None:
    violations = {
        str(path.relative_to(SOURCE_ROOT)): imported
        for path in _files("runtime")
        for imported in _imports(path)
        if imported.startswith("mdhelper.integrations")
    }
    assert violations == {}


def test_analysis_engines_do_not_execute_processes_directly() -> None:
    violations = {
        str(path.relative_to(SOURCE_ROOT)): imported
        for package in ("analysis", "backends")
        for path in _files(package)
        for imported in _imports(path)
        if imported == "subprocess" or imported.startswith("mdhelper.runtime")
    }
    assert violations == {}


def test_analysis_computation_does_not_import_plotting() -> None:
    violations = {
        str(path.relative_to(SOURCE_ROOT)): imported
        for path in _files("analysis")
        for imported in _imports(path)
        if imported == "mdhelper.core.plotting" or imported.startswith(
            "mdhelper.core.plotting."
        )
    }
    assert violations == {}
