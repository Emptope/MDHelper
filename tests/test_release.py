from __future__ import annotations

import json
import re
import runpy
import subprocess
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml
from packaging.requirements import Requirement

ROOT = Path(__file__).parents[1]
SCRIPT = Path(__file__).parents[1] / "packaging" / "check_release.py"
CLEAN_SCRIPT = Path(__file__).parents[1] / "packaging" / "clean_build.py"
FROZEN_AUDIT = runpy.run_path(str(ROOT / "packaging" / "frozen_audit.py"))
SMOKE_CHECK = runpy.run_path(str(ROOT / "packaging" / "smoke_check.py"))


def write_distribution(root: Path, platform: str) -> Path:
    root.mkdir()
    application = root / ("mdhelper.exe" if platform == "windows" else "mdhelper")
    application.write_bytes(b"application")
    application.chmod(0o755)
    for name in (
        "LICENSE",
        "README.md",
        "README.zh-CN.md",
        "config.example.toml",
        "config.toml",
    ):
        (root / name).write_text(name, encoding="ascii")
    for directory, name in (
        ("docs", "guide.md"),
        ("licenses", "notices.json"),
        ("schemas", "contract.json"),
    ):
        target = root / directory
        target.mkdir()
        (target / name).write_text("{}", encoding="ascii")
    return application


def write_metadata(root: Path, project_version: str, source_version: str) -> None:
    (root / "src" / "mdhelper").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "sample"\nversion = "{project_version}"\n',
        encoding="utf-8",
    )
    (root / "src" / "mdhelper" / "version.py").write_text(
        f'__version__ = "{source_version}"\n',
        encoding="utf-8",
    )


def run_check(root: Path, tag: str | None = None) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(SCRIPT), "--root", str(root)]
    if tag is not None:
        command.extend(("--tag", tag))
    return subprocess.run(command, capture_output=True, check=False, text=True)


def test_tag_release_graph_does_not_repeat_commit_tests() -> None:
    workflows = {
        path: yaml.load(path.read_text(encoding="ascii"), Loader=yaml.BaseLoader)
        for path in (ROOT / ".github" / "workflows").glob("*.yml")
    }
    pending = [
        path for path, workflow in workflows.items()
        if workflow.get("on", {}).get("push", {}).get("tags")
    ]
    assert pending
    checked = set()
    while pending:
        path = pending.pop()
        if path in checked:
            continue
        checked.add(path)
        for job in workflows[path]["jobs"].values():
            reference = job.get("uses", "")
            if reference.startswith(("./", "$/")):
                pending.append(ROOT / reference[2:])
            for step in job.get("steps", []):
                command = step.get("run", "")
                assert not re.search(
                    r"\b(?:ruff|mypy|pytest|SmokeRequest|SMOKE_REQUEST)\b|--smoke-test",
                    command,
                ), (path, command)


@pytest.mark.parametrize("spec", sorted((ROOT / "packaging").rglob("*.spec")))
def test_freezer_specs_reference_existing_resources(spec: Path, monkeypatch) -> None:
    from PIL import Image

    monkeypatch.setenv("MDHELPER_GUI_BUILD", "1")
    analysis = Mock(return_value=SimpleNamespace(
        pure=[], scripts=[], binaries=[], datas=[], dependencies=[],
    ))
    executable = Mock()
    runpy.run_path(str(spec), init_globals={
        "SPECPATH": str(spec.parent), "Analysis": analysis, "PYZ": Mock(), "EXE": executable,
    })
    analysis.assert_called_once()
    executable.assert_called_once()
    args, options = analysis.call_args
    for source in args[0]:
        assert Path(source).is_file()
    for directory in (*options["pathex"], *options["hookspath"]):
        assert Path(directory).is_dir()
    assert options["datas"]
    for source, destination in options["datas"]:
        assert Path(source).exists()
        assert destination and not Path(destination).is_absolute()
    icon = executable.call_args.kwargs.get("icon")
    if icon is not None:
        with Image.open(icon) as image:
            image.load()
            assert image.width > 0 and image.height > 0


def test_build_cleanup_removes_only_generated_tree(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[build-system]\n", encoding="utf-8")
    build = tmp_path / "build"
    build.mkdir()
    (build / "stale.txt").write_text("stale", encoding="utf-8")
    source = tmp_path / "source.txt"
    source.write_text("keep", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(CLEAN_SCRIPT), "--root", str(tmp_path)],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0
    assert not build.exists()
    assert source.read_text(encoding="utf-8") == "keep"


def test_build_cleanup_rejects_non_project_root(tmp_path: Path) -> None:
    build = tmp_path / "build"
    build.mkdir()

    result = subprocess.run(
        [sys.executable, str(CLEAN_SCRIPT), "--root", str(tmp_path)],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode != 0
    assert build.is_dir()


def test_release_check_accepts_matching_versions_and_tag(tmp_path: Path) -> None:
    write_metadata(tmp_path, "2.4.6", "2.4.6")

    result = run_check(tmp_path, "v2.4.6")

    assert result.returncode == 0
    assert result.stdout.strip() == "2.4.6"


def test_release_check_rejects_source_version_mismatch(tmp_path: Path) -> None:
    write_metadata(tmp_path, "2.4.6", "2.4.7")

    result = run_check(tmp_path)

    assert result.returncode != 0
    assert "Project and source versions differ" in result.stderr


def test_release_check_rejects_tag_version_mismatch(tmp_path: Path) -> None:
    write_metadata(tmp_path, "2.4.6", "2.4.6")

    result = run_check(tmp_path, "v3.5.7")

    assert result.returncode != 0
    assert "Release tag does not match version" in result.stderr


def test_release_check_rejects_invalid_tag(tmp_path: Path) -> None:
    write_metadata(tmp_path, "2.4.6", "2.4.6")

    result = run_check(tmp_path, "release-2.4.6")

    assert result.returncode != 0
    assert "Release tag must use v<version>" in result.stderr


@pytest.mark.parametrize(
    ("platform", "entries", "expected"),
    [
        (
            "windows",
            ["PySide6/plugins/platforms/qoffscreen.dll"],
            ["qwindows.dll"],
        ),
        (
            "linux-gui",
            [
                "PySide6/Qt/plugins/platforms/libqoffscreen.so",
                "PySide6/Qt/plugins/platforms/libqwayland.so",
            ],
            ["libqxcb.so"],
        ),
        ("linux", [], []),
        ("macos", ["PySide6/Qt/plugins/platforms/libqoffscreen.dylib"], ["libqcocoa.dylib"]),
        ("macos", ["PySide6/Qt/plugins/platforms/libqcocoa.dylib"], []),
    ],
)
def test_frozen_audit_requires_runtime_qt_plugins(
    platform: str,
    entries: list[str],
    expected: list[str],
) -> None:
    assert FROZEN_AUDIT["missing_plugins"](entries, platform) == expected


@pytest.mark.parametrize("platform", ["linux", "linux-gui", "windows", "macos"])
def test_smoke_check_validates_distribution_contract(
    tmp_path: Path, platform: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    distribution = tmp_path / "distribution"
    application = write_distribution(distribution, platform)
    executable_paths = {application}
    monkeypatch.setattr(SMOKE_CHECK["os"], "access", lambda path, _mode: path in executable_paths)

    assert SMOKE_CHECK["validate_distribution"](distribution, platform) == application
    extra = application.with_name("unexpected" + application.suffix)
    extra.write_bytes(b"application")
    executable_paths.add(extra)
    with pytest.raises(SMOKE_CHECK["SmokeFailure"], match="only the packaged application"):
        SMOKE_CHECK["validate_distribution"](distribution, platform)
    extra.unlink()

    (distribution / "schemas" / "contract.json").unlink()
    with pytest.raises(SMOKE_CHECK["SmokeFailure"], match="schemas"):
        SMOKE_CHECK["validate_distribution"](distribution, platform)


@pytest.mark.parametrize(
    ("system", "machine", "gui"),
    [("linux", "x86_64", False), ("win32", "AMD64", True), ("darwin", "arm64", True)],
)
def test_desktop_dependency_selection(system: str, machine: str, gui: bool) -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    requirements = [Requirement(value) for value in project["dependencies"]]
    qt = next(item for item in requirements if item.name == "PySide6")
    assert qt.marker is not None
    assert qt.marker.evaluate({"sys_platform": system, "platform_machine": machine}) is gui


def test_macos_payload_policy() -> None:
    allowed = [
        "PySide6/Qt/plugins/platforms/libqcocoa.dylib",
        "PySide6/Qt/plugins/platforms/libqoffscreen.dylib",
        "PySide6/Qt/lib/QtCore.framework/Versions/A/QtCore",
    ]
    forbidden = [
        "PySide6/Qt/plugins/platforms/libqminimal.dylib",
        "PySide6/Qt/translations/qtbase_en.qm",
        "pytest/__init__.py",
    ]
    assert FROZEN_AUDIT["violations"](allowed + forbidden, "macos") == forbidden


def test_smoke_check_rejects_empty_distribution_directory(tmp_path: Path) -> None:
    distribution = tmp_path / "distribution"
    write_distribution(distribution, "linux")
    for path in (distribution / "docs").iterdir():
        path.unlink()

    with pytest.raises(SMOKE_CHECK["SmokeFailure"], match="docs"):
        SMOKE_CHECK["validate_distribution"](distribution, "linux")


def test_smoke_check_rejects_invalid_archive_layout(tmp_path: Path) -> None:
    expected = tmp_path / "release"
    expected.mkdir()

    assert SMOKE_CHECK["validate_archive_root"](tmp_path, "release") == expected

    (tmp_path / "extra").mkdir()
    with pytest.raises(SMOKE_CHECK["SmokeFailure"], match="one root directory"):
        SMOKE_CHECK["validate_archive_root"](tmp_path, "release")


def test_smoke_check_validates_reported_exports_without_fixed_stem(
    tmp_path: Path,
) -> None:
    output = tmp_path / "analysis"
    output.mkdir()
    names = (
        "result.json",
        "custom.csv",
        "custom.png",
        "custom.svg",
        "custom.pdf",
    )
    for name in names:
        content = '{"schema_version": 1, "analysis_type": "energy"}'
        (output / name).write_text(content, encoding="ascii")
    report = json.dumps(
        {
            "status": "completed",
            "analysis_type": "energy",
            "exports": [str(output / name) for name in names],
        }
    )

    SMOKE_CHECK["validate_analysis"](output, report)

    (output / "custom.pdf").unlink()
    with pytest.raises(SMOKE_CHECK["SmokeFailure"], match="missing export"):
        SMOKE_CHECK["validate_analysis"](output, report)


def test_smoke_check_rejects_export_outside_output(tmp_path: Path) -> None:
    output = tmp_path / "analysis"
    output.mkdir()
    external = tmp_path / "external.json"
    external.write_text('{"schema_version": 1, "analysis_type": "energy"}', encoding="ascii")
    report = json.dumps(
        {
            "status": "completed",
            "analysis_type": "energy",
            "exports": [str(external)],
        }
    )

    with pytest.raises(SMOKE_CHECK["SmokeFailure"], match="outside"):
        SMOKE_CHECK["validate_analysis"](output, report)


def test_smoke_check_rejects_result_type_mismatch(tmp_path: Path) -> None:
    output = tmp_path / "analysis"
    output.mkdir()
    exports = []
    for suffix in ("json", "csv", "png", "svg", "pdf"):
        path = output / f"custom.{suffix}"
        path.write_text(
            '{"schema_version": 1, "analysis_type": "rdf"}',
            encoding="ascii",
        )
        exports.append(str(path))
    report = json.dumps(
        {
            "status": "completed",
            "analysis_type": "energy",
            "exports": exports,
        }
    )

    with pytest.raises(SMOKE_CHECK["SmokeFailure"], match="analysis type"):
        SMOKE_CHECK["validate_analysis"](output, report)


def test_smoke_check_validates_config_report(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text("", encoding="ascii")
    report = json.dumps(
        {
            "status": "valid",
            "path": str(config),
            "exists": True,
            "configuration": {},
        }
    )

    SMOKE_CHECK["validate_config"](report, config)

    wrong = tmp_path / "wrong.toml"
    with pytest.raises(SMOKE_CHECK["SmokeFailure"], match="configuration path"):
        SMOKE_CHECK["validate_config"](report, wrong)
