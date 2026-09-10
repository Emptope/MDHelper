from __future__ import annotations

import json
import runpy
import struct
import subprocess
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
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
    if platform == "windows":
        application.with_suffix(".com").write_bytes(b"console")
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


@pytest.mark.parametrize("platform", ["linux", "darwin", "win32"])
def test_freezer_specs_reference_existing_resources(platform: str, monkeypatch) -> None:
    from PIL import Image

    spec = ROOT / "packaging" / ("windows" if platform == "win32" else "posix")
    spec /= "mdhelper.spec"
    monkeypatch.setenv("MDHELPER_GUI_BUILD", "1")
    monkeypatch.setattr(sys, "platform", platform)
    analysis = Mock(return_value=SimpleNamespace(
        pure=[], scripts=[], binaries=[], datas=[], dependencies=[],
    ))
    executable, collect, bundle = Mock(), Mock(), Mock()
    runpy.run_path(str(spec), init_globals={
        "SPECPATH": str(spec.parent), "Analysis": analysis, "PYZ": Mock(), "EXE": executable,
        "COLLECT": collect, "BUNDLE": bundle,
    })
    if platform == "darwin":
        assert executable.call_args.kwargs["exclude_binaries"] is True
        assert executable.call_args.args[2:4] == ([], [])
        collect.assert_called_once()
        bundle.assert_called_once()
        assert bundle.call_args.args == (collect.return_value,)
        assert bundle.call_args.kwargs["name"] == "MDHelper.app"
        assert Path(bundle.call_args.kwargs["icon"]).is_file()
        assert bundle.call_args.kwargs["version"]
        # Keep terminal adapters without registering a background-only app.
        assert executable.call_args.kwargs["console"] is True
        info = bundle.call_args.kwargs["info_plist"]
        assert info["LSBackgroundOnly"] is False
        assert info["LSUIElement"] is False
    else:
        assert not executable.call_args.kwargs.get("exclude_binaries", False)
        collect.assert_not_called()
        bundle.assert_not_called()
        if platform == "win32":
            assert executable.call_args.kwargs["console"] is False
            assert "hide_console" not in executable.call_args.kwargs
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


@pytest.mark.parametrize("subsystem", [2, 3])
@pytest.mark.parametrize("console", [False, True])
def test_windows_audit_checks_the_requested_interface_subsystem(
    tmp_path: Path, subsystem: int, console: bool,
) -> None:
    application = tmp_path / "launcher.exe"
    header = bytearray(64 + 94)
    header[:2] = b"MZ"
    struct.pack_into("<I", header, 0x3C, 64)
    header[64:68] = b"PE\0\0"
    struct.pack_into("<H", header, 64 + 24, 0x20B)
    struct.pack_into("<H", header, 64 + 24 + 68, subsystem)
    application.write_bytes(header)
    if subsystem == (3 if console else 2):
        FROZEN_AUDIT["check_subsystem"](application, "windows", console=console)
    else:
        with pytest.raises(SystemExit, match="subsystem"):
            FROZEN_AUDIT["check_subsystem"](application, "windows", console=console)


@pytest.mark.parametrize("extra", [None, "runtime.dll", "dependencies"])
def test_windows_distribution_requires_encapsulated_dependencies(
    tmp_path: Path, extra: str | None,
) -> None:
    distribution = tmp_path / "distribution"
    application = write_distribution(distribution, "windows")
    if extra is None:
        application.with_suffix(".com").unlink()
    elif Path(extra).suffix:
        (distribution / extra).write_bytes(b"dependency")
    else:
        (distribution / extra).mkdir()
    with pytest.raises(SMOKE_CHECK["SmokeFailure"]):
        SMOKE_CHECK["validate_distribution"](distribution, "windows")


def test_windows_audit_keeps_the_forwarder_small_and_the_payload_unique(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = tmp_path / "application.exe"
    terminal = application.with_suffix(".com")
    application.write_bytes(b"payload")
    terminal.write_bytes(b"forwarder")
    globals_ = FROZEN_AUDIT["audit"].__globals__
    monkeypatch.setitem(globals_, "windows_subsystem", {application: 2, terminal: 3}.__getitem__)
    archive = Mock(return_value=(["PySide6/plugins/platforms/qwindows.dll"], []))
    monkeypatch.setitem(globals_, "archive", archive)
    FROZEN_AUDIT["audit"](application, "windows", 256)
    archive.assert_called_once_with(application)
    terminal.write_bytes(b"x" * 1_000_001)
    with pytest.raises(SystemExit, match="limit"):
        FROZEN_AUDIT["audit"](application, "windows", 256)


def test_native_toolchain_initializes_the_installed_build_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launcher = runpy.run_path(str(ROOT / "packaging/windows/launcher.py"))
    monkeypatch.setenv("PROGRAMFILES(X86)", "C:/Program Files (x86)")
    compiler = "D:/compiler/cl.exe"
    which = Mock(side_effect=[None, None, compiler])
    monkeypatch.setattr(launcher["shutil"], "which", which)
    output = Mock(side_effect=["D:/Build Tools\n", "PATH=D:/compiler\nLIB=D:/libraries\n"])
    monkeypatch.setattr(launcher["subprocess"], "check_output", output)
    found, environment = launcher["toolchain"]()
    assert found == compiler
    assert environment["LIB"] == "D:/libraries"
    which.assert_called_with("cl", path=environment["PATH"])


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


@pytest.mark.parametrize("platform", ["linux", "linux-gui", "windows"])
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
    with pytest.raises(SMOKE_CHECK["SmokeFailure"], match="packaged application"):
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
