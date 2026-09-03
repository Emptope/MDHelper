from __future__ import annotations

import ast
from functools import cache
from pathlib import Path

SOURCE_ROOT = Path(__file__).parents[1] / "src" / "mdhelper"
PRESENTATION_PACKAGES = ("cli", "gui", "tui")
PRESENTATION_PREFIXES = tuple(f"mdhelper.{name}" for name in PRESENTATION_PACKAGES)


def _module(path: Path) -> str:
    relative = path.relative_to(SOURCE_ROOT.parent).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


@cache
def _imports(path: Path, loading_only: bool = False) -> tuple[str, ...]:
    package = _module(path)
    if path.name != "__init__.py":
        package = package.rpartition(".")[0]
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[str] = []
    nodes = tree.body if loading_only else ast.walk(tree)
    for node in nodes:
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


def _files(package: str) -> tuple[Path, ...]:
    return tuple((SOURCE_ROOT / package).rglob("*.py"))


def _violations(packages: tuple[str, ...], prefixes: tuple[str, ...]) -> dict[str, str]:
    return {
        str(path.relative_to(SOURCE_ROOT)): imported
        for package in packages
        for path in _files(package)
        for imported in _imports(path)
        if imported.startswith(prefixes)
    }


def _internal_graph() -> dict[str, set[str]]:
    modules = {_module(path): path for path in SOURCE_ROOT.rglob("*.py")}
    graph: dict[str, set[str]] = {}
    for module, path in modules.items():
        targets: set[str] = set()
        for imported in _imports(path, loading_only=True):
            target = imported
            while target not in modules and "." in target:
                target = target.rpartition(".")[0]
            if target in modules and target != module:
                targets.add(target)
        graph[module] = targets
    return graph


def _package_graph(graph: dict[str, set[str]]) -> dict[str, set[str]]:
    packages = {
        module.split(".", maxsplit=2)[1]
        for module in graph
        if module.startswith("mdhelper.")
    }
    result = {package: set() for package in packages}
    for module, targets in graph.items():
        if not module.startswith("mdhelper."):
            continue
        source = module.split(".", maxsplit=2)[1]
        for target in targets:
            if not target.startswith("mdhelper."):
                continue
            destination = target.split(".", maxsplit=2)[1]
            if destination != source:
                result[source].add(destination)
    return result


def _cycles(graph: dict[str, set[str]]) -> set[tuple[str, ...]]:
    found: set[tuple[str, ...]] = set()
    active: list[str] = []
    visited: set[str] = set()

    def visit(module: str) -> None:
        if module in active:
            start = active.index(module)
            found.add(tuple((*active[start:], module)))
            return
        if module in visited:
            return
        active.append(module)
        for target in graph[module]:
            visit(target)
        active.pop()
        visited.add(module)

    for module in graph:
        visit(module)
    return found


def test_core_has_no_reverse_internal_dependencies() -> None:
    violations = {
        str(path.relative_to(SOURCE_ROOT)): imported
        for path in _files("core")
        for imported in _imports(path)
        if imported.startswith("mdhelper.") and not imported.startswith("mdhelper.core")
    }
    assert violations == {}


def test_internal_module_dependencies_are_acyclic() -> None:
    assert _cycles(_internal_graph()) == set()


def test_top_level_package_dependencies_are_acyclic() -> None:
    assert _cycles(_package_graph(_internal_graph())) == set()


def test_persistence_does_not_depend_on_service_orchestration() -> None:
    assert _violations(("io", "project"), ("mdhelper.services",)) == {}


def test_presentations_depend_on_application_boundaries() -> None:
    assert _violations(
        PRESENTATION_PACKAGES,
        ("mdhelper.analysis", "mdhelper.backends"),
    ) == {}


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


def test_qt_is_confined_to_gui_adapters() -> None:
    assert _violations(
        tuple(
            path.name
            for path in SOURCE_ROOT.iterdir()
            if path.is_dir() and path.name != "gui"
        ),
        ("PySide6",),
    ) == {}
    state_violations = {
        str(path.relative_to(SOURCE_ROOT)): imported
        for path in (SOURCE_ROOT / "gui").rglob("*state.py")
        for imported in _imports(path)
        if imported.startswith("PySide6")
    }
    assert state_violations == {}


def test_process_execution_stays_behind_integration_boundaries() -> None:
    assert _violations(("runtime",), ("mdhelper.integrations",)) == {}
    assert _violations(
        ("analysis", "backends"),
        ("mdhelper.runtime", "subprocess"),
    ) == {}


def test_analysis_computation_does_not_depend_on_plotting() -> None:
    assert _violations(("analysis",), ("mdhelper.core.plotting",)) == {}
