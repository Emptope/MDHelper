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
    "windows.py",
}
GUI_SUBPACKAGES = {"actions", "components", "controllers", "dialogs", "pages", "plotting"}
GUI_ACTION_MODULES = {
    "__init__.py",
    "analysis.py",
    "backend.py",
    "project.py",
    "results.py",
}
GUI_ACTION_SUBPACKAGES = {"system"}
GUI_SYSTEM_ACTION_MODULES = {
    "__init__.py",
    "help.py",
    "inspection.py",
    "roles.py",
    "watching.py",
}
GUI_PAGE_MODULES = {
    "__init__.py",
    "analysis.py",
    "load.py",
    "results.py",
    "workspace.py",
}
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
TUI_ANALYSIS_MODULES = {
    "__init__.py",
    "navigation.py",
    "parameters.py",
    "queue.py",
}
JOB_MODULES = {"__init__.py", "models.py", "runner.py"}
ANALYSIS_PIPELINE_MODULES = {"__init__.py", "models.py", "registry.py"}
RADIAL_MODULES = {
    "__init__.py",
    "curves.py",
    "execution.py",
    "frames.py",
    "neighbors.py",
    "shells.py",
}
CORE_ANALYSIS_MODULES = {
    "__init__.py",
    "requests.py",
    "results.py",
    "validation.py",
}
CORE_PLOTTING_MODULES = {
    "__init__.py",
    "appearance.py",
    "builders.py",
    "models.py",
    "rendering.py",
    "state.py",
}
IO_EXPORT_MODULES = {"__init__.py", "figures.py", "paths.py", "structured.py"}
RUNTIME_PROCESS_MODULES = {
    "__init__.py",
    "contracts.py",
    "lifecycle.py",
    "records.py",
    "terminal.py",
}
SERVICE_CONFIG_MODULES = {
    "__init__.py",
    "contracts.py",
    "parsing.py",
    "storage.py",
}
MODULE_LAYERS = {
    "core/analysis": {
        "validation": 0,
        "requests": 1,
        "results": 2,
        "__init__": 3,
    },
    "core/plotting": {
        "models": 0,
        "appearance": 0,
        "state": 1,
        "builders": 2,
        "rendering": 2,
        "__init__": 3,
    },
    "app/analysis": {"execution": 0, "plans": 0, "exports": 1, "__init__": 2},
    "analysis/pipeline": {"models": 0, "registry": 1, "__init__": 2},
    "analysis/radial": {
        "frames": 0,
        "shells": 0,
        "curves": 1,
        "neighbors": 1,
        "execution": 2,
        "__init__": 3,
    },
    "io/export": {"paths": 0, "structured": 1, "figures": 1, "__init__": 2},
    "runtime/process": {
        "contracts": 0,
        "records": 1,
        "terminal": 2,
        "lifecycle": 2,
        "__init__": 3,
    },
    "services/config": {
        "contracts": 0,
        "parsing": 1,
        "storage": 2,
        "__init__": 3,
    },
    "tui/controllers/analysis": {
        "parameters": 0,
        "queue": 1,
        "navigation": 2,
        "__init__": 3,
    },
    "analysis/gromacs": {
        "inputs": 0,
        "curves": 0,
        "runs": 0,
        "backend": 1,
        "__init__": 2,
    },
    "gui/plotting": {
        "state": 0,
        "window": 0,
        "settings": 0,
        "table": 1,
        "controls": 2,
        "panel": 3,
        "__init__": 4,
    },
    "gui/actions/system": {
        "inspection": 0,
        "watching": 1,
        "roles": 2,
        "help": 3,
        "__init__": 4,
    },
}
GUI_FORBIDDEN_IMPORTS = {
    "components": ("actions", "controllers", "dialogs", "pages"),
    "controllers": ("actions", "components", "dialogs", "pages"),
    "dialogs": ("actions", "controllers", "pages"),
    "pages": ("actions", "controllers"),
    "plotting": ("actions", "controllers", "dialogs", "pages"),
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


def test_layered_module_groups_follow_dependency_direction() -> None:
    violations = {
        str(path.relative_to(SOURCE_ROOT)): imported
        for package, layers in MODULE_LAYERS.items()
        for path in (SOURCE_ROOT / package).glob("*.py")
        for imported in _imports(path)
        if imported.startswith(f"mdhelper.{package.replace('/', '.')}.")
        and imported.rpartition(".")[2] in layers
        and layers[imported.rpartition(".")[2]] >= layers[path.stem]
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


def test_gui_state_modules_do_not_import_qt() -> None:
    violations = {
        str(path.relative_to(SOURCE_ROOT)): imported
        for path in (SOURCE_ROOT / "gui").rglob("*state.py")
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


def test_gui_actions_have_focused_module_layout() -> None:
    root = SOURCE_ROOT / "gui" / "actions"
    assert {path.name for path in root.glob("*.py")} == GUI_ACTION_MODULES
    packages = {
        path.name
        for path in root.iterdir()
        if path.is_dir() and (path / "__init__.py").is_file()
    }
    assert packages == GUI_ACTION_SUBPACKAGES


def test_gui_system_actions_have_focused_module_layout() -> None:
    system = SOURCE_ROOT / "gui" / "actions" / "system"

    assert {path.name for path in system.glob("*.py")} == GUI_SYSTEM_ACTION_MODULES


def test_gui_pages_have_focused_module_layout() -> None:
    root = SOURCE_ROOT / "gui" / "pages"
    assert {path.name for path in root.glob("*.py")} == GUI_PAGE_MODULES


def test_non_modal_window_presentation_is_centralized() -> None:
    methods = {"activateWindow", "raise_"}
    violations = {
        str(path.relative_to(SOURCE_ROOT)): node.func.attr
        for path in _files("gui")
        if path.name != "windows.py"
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in methods
    }
    assert violations == {}


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


def test_tui_analysis_controllers_have_focused_module_layout() -> None:
    analysis = SOURCE_ROOT / "tui" / "controllers" / "analysis"

    assert {path.name for path in analysis.glob("*.py")} == TUI_ANALYSIS_MODULES


def test_job_execution_and_workflow_packages_are_separate() -> None:
    jobs = SOURCE_ROOT / "jobs"
    workflow = SOURCE_ROOT / "workflow"

    assert {path.name for path in jobs.glob("*.py")} == JOB_MODULES
    assert {path.name for path in workflow.glob("*.py")} == {"__init__.py"}
    assert _imports(workflow / "__init__.py") == ()


def test_analysis_pipeline_contracts_have_focused_layout() -> None:
    pipeline = SOURCE_ROOT / "analysis" / "pipeline"

    assert {path.name for path in pipeline.glob("*.py")} == ANALYSIS_PIPELINE_MODULES


def test_radial_analysis_has_focused_module_layout() -> None:
    radial = SOURCE_ROOT / "analysis" / "radial"

    assert {path.name for path in radial.glob("*.py")} == RADIAL_MODULES


def test_core_contracts_have_focused_module_layout() -> None:
    analysis = SOURCE_ROOT / "core" / "analysis"
    plotting = SOURCE_ROOT / "core" / "plotting"

    assert {path.name for path in analysis.glob("*.py")} == CORE_ANALYSIS_MODULES
    assert {path.name for path in plotting.glob("*.py")} == CORE_PLOTTING_MODULES


def test_export_adapters_have_focused_module_layout() -> None:
    export = SOURCE_ROOT / "io" / "export"

    assert {path.name for path in export.glob("*.py")} == IO_EXPORT_MODULES


def test_process_runtime_has_focused_module_layout() -> None:
    process = SOURCE_ROOT / "runtime" / "process"

    assert {path.name for path in process.glob("*.py")} == RUNTIME_PROCESS_MODULES


def test_configuration_service_has_focused_module_layout() -> None:
    config = SOURCE_ROOT / "services" / "config"

    assert {path.name for path in config.glob("*.py")} == SERVICE_CONFIG_MODULES


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
