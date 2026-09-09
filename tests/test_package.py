from __future__ import annotations

import os
import plistlib
import runpy
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).parents[1]
PACKAGE = runpy.run_path(str(ROOT / "packaging" / "posix" / "dmg.py"))
SMOKE = runpy.run_path(str(ROOT / "packaging" / "smoke_check.py"))


def make_bundle(tmp_path: Path) -> Path:
    source = tmp_path / "portable"
    source.mkdir()
    executable = source / "mdhelper"
    executable.write_bytes(b"application")
    executable.chmod(0o755)
    for name in SMOKE["REQUIRED_FILES"]:
        (source / name).write_text("example", encoding="ascii")
    for name in SMOKE["REQUIRED_DIRECTORIES"]:
        (source / name).mkdir()
        (source / name / "data.json").write_text("{}", encoding="ascii")
    icon = tmp_path / "icon.png"
    Image.new("RGBA", (1024, 1024), "red").save(icon)
    bundle = tmp_path / "image" / "Sample App.app"
    PACKAGE["create_bundle"](source, bundle, "2.4.6", icon)
    return bundle


def test_bundle_preserves_payload_and_registers_executable(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path)
    contents = bundle / "Contents"
    with (contents / "Info.plist").open("rb") as handle:
        info = plistlib.load(handle)
    executable = contents / "MacOS" / info["CFBundleExecutable"]
    assert executable.read_bytes() == b"application"
    assert info["CFBundlePackageType"] == "APPL"
    assert info["CFBundleShortVersionString"] == "2.4.6"
    resources = contents / "Resources"
    with Image.open(resources / info["CFBundleIconFile"]) as image:
        image.load()
        assert image.width > 0
    assert not list(bundle.rglob("config.toml"))
    assert (resources / "config.example.toml").is_file()
    assert SMOKE["validate_distribution"](bundle, "macos") == executable
    renamed = executable.with_name("renamed-launcher")
    executable.rename(renamed)
    info["CFBundleExecutable"] = renamed.name
    with (contents / "Info.plist").open("wb") as handle:
        plistlib.dump(info, handle)
    assert SMOKE["validate_distribution"](bundle, "macos") == renamed


@pytest.mark.parametrize("smoke, fail_copy", [(False, False), (True, False), (True, True)])
def test_dmg_audits_and_cleans_up_installation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, smoke: bool, fail_copy: bool,
) -> None:
    make_bundle(tmp_path)
    commands: list[tuple[str, ...]] = []
    environments: list[dict[str, str]] = []
    image: Path | None = None

    def run(command: tuple[str, ...], *, check: bool, env: dict[str, str] | None) -> None:
        nonlocal image
        assert check
        commands.append(command)
        if command[:2] == ("hdiutil", "create"):
            image = Path(command[command.index("-srcfolder") + 1])
            assert "-format" in command and "UDZO" in command
            Path(command[-1]).write_bytes(b"image")
        if command[0] == "ditto":
            if fail_copy:
                raise subprocess.CalledProcessError(1, command)
            assert image is not None
            shutil.copytree(image / Path(command[1]).name, command[2])
        if command[0] == "bash":
            assert env is not None
            environments.append(env)
            assert Path(command[2]).is_dir()
            assert Path(env["HOME"]).is_dir()

    monkeypatch.setattr(PACKAGE["subprocess"], "run", run)
    links: list[tuple[Path, str]] = []
    monkeypatch.setattr(
        Path, "symlink_to",
        lambda path, target, **kwargs: links.append((path, target)),
    )
    monkeypatch.setattr(Path, "readlink", lambda path: Path(links[0][1]))
    monkeypatch.setenv("MDHELPER_CONFIG", str(tmp_path / "existing.toml"))
    artifact = tmp_path / "release.dmg"
    request = tmp_path / "request.json" if smoke else None
    if fail_copy:
        with pytest.raises(subprocess.CalledProcessError):
            PACKAGE["create_dmg"](tmp_path / "portable", artifact, "2.4.6", request)
    else:
        PACKAGE["create_dmg"](tmp_path / "portable", artifact, "2.4.6", request)
    assert image is not None and not image.parent.exists()
    assert links[0][1] == "/Applications"
    assert ("hdiutil", "verify", str(artifact)) in commands
    assert any("--artifact" in command for command in commands)
    actions = [command[:2] for command in commands]
    if smoke:
        assert ("hdiutil", "attach") in actions
        assert ("hdiutil", "detach") in actions
        attach = commands[actions.index(("hdiutil", "attach"))]
        assert "-readonly" in attach
        if not fail_copy:
            launch = next(i for i, command in enumerate(commands) if command[0] == "bash")
            assert actions.index(("hdiutil", "detach")) < launch
            assert "MDHELPER_CONFIG" not in environments[0]
            assert commands[-1][0] == "open"
    else:
        assert ("hdiutil", "attach") not in actions
        assert not environments


@pytest.mark.skipif(sys.platform == "win32", reason="Requires a POSIX build host")
@pytest.mark.parametrize("failure", ["", "update", "install"])
def test_linux_gui_dependency_installation(tmp_path: Path, failure: str) -> None:
    script = ROOT / "packaging" / "posix" / "install-deps.sh"
    log = tmp_path / "commands.log"
    result = subprocess.run(
        ["bash", "-c", '''
sudo() {
    printf '%s\\n' "$*" >> "$COMMAND_LOG"
    if [[ "$2" == "$FAILURE" ]]; then return 23; fi
}
source "$1"
''', "bash", str(script)],
        env=dict(os.environ, COMMAND_LOG=str(log), FAILURE=failure),
        capture_output=True, text=True, check=False,
    )
    commands = [line.split() for line in log.read_text(encoding="ascii").splitlines()]
    assert commands[0] == ["apt-get", "update"]
    if failure:
        assert result.returncode == 23, result.stderr
        assert len(commands) == (1 if failure == "update" else 2)
        return
    assert result.returncode == 0, result.stderr
    assert commands[1][:2] == ["apt-get", "install"]
    assert "--yes" in commands[1]
    # Runtime packages required by the EGL and XCB platform integrations.
    required = {
        "libegl1", "libxcb-cursor0", "libxcb-icccm4", "libxcb-image0",
        "libxcb-keysyms1", "libxcb-render-util0", "libxcb-shape0",
        "libxcb-util1", "libxcb-xkb1", "libxkbcommon-x11-0",
    }
    assert required <= set(commands[1][2:])


@pytest.mark.skipif(sys.platform == "win32", reason="Requires a POSIX build host")
@pytest.mark.parametrize("smoke", [False, True])
@pytest.mark.parametrize("outcome", ["created", "failed", "missing", "empty", "expansion"])
def test_posix_build_requires_release_artifact(
    tmp_path: Path, smoke: bool, outcome: str,
) -> None:
    project = tmp_path / "project with spaces"
    scripts = project / "packaging" / "posix"
    scripts.mkdir(parents=True)
    shutil.copy2(ROOT / "packaging" / "posix" / "build.sh", scripts / "build.sh")
    for name in ("LICENSE", "README.md", "README.zh-CN.md", "config.example.toml"):
        (project / name).write_text("payload", encoding="ascii")
    for name in ("docs", "schemas"):
        (project / name).mkdir()
    driver = tmp_path / "driver.sh"
    driver.write_text(
        """set -euo pipefail
uname() {
    case "$1" in
        -s) printf 'Darwin\\n' ;;
        -m) printf 'arm64\\n' ;;
    esac
}
lipo() { printf 'arm64\\n'; }
codesign() { return 0; }
python() {
    case "$1" in
        -c) return 0 ;;
        */check_release.py) printf '%s\\n' "$VERSION" ;;
        */clean_build.py) rm -rf -- "$PROJECT/build" ;;
        -m)
            test ! -e "$PROJECT/build/stale"
            while [[ "$1" != --distpath ]]; do shift; done
            mkdir -p "$2"
            printf 'application' > "$2/mdhelper"
            ;;
        */dmg.py)
            shift
            local artifact= request=
            while [[ $# -gt 0 ]]; do
                case "$1" in
                    --artifact) artifact=$2 ;;
                    --request) request=$2 ;;
                esac
                shift 2
            done
            test "$request" = "${SMOKE_REQUEST:-}"
            case "$OUTCOME" in
                created) printf 'image' > "$artifact" ;;
                failed) return 23 ;;
                missing) return 0 ;;
                empty) touch "$artifact" ;;
                expansion) printf '%s' "${1:?missing command argument}" ;;
            esac
            ;;
    esac
}
source "$PROJECT/packaging/posix/build.sh" macos
""",
        encoding="ascii",
    )
    (project / "build").mkdir()
    (project / "build" / "stale").touch()
    version = "3.5.7"
    environment = dict(os.environ, PROJECT=str(project), VERSION=version, OUTCOME=outcome)
    environment.pop("SMOKE_REQUEST", None)
    environment["PYTHON"] = "python"
    if smoke:
        environment["SMOKE_REQUEST"] = str(project / "smoke request.json")
    result = subprocess.run(
        ["bash", str(driver)], env=environment, capture_output=True, text=True, check=False,
    )
    artifact = project / "dist" / "macos" / f"MDHelper-{version}-macOS-arm64.dmg"
    if outcome == "created":
        assert result.returncode == 0, result.stderr
        assert artifact.is_file(), result.stderr
    else:
        assert result.returncode != 0, result.stderr
        assert not artifact.exists() or artifact.stat().st_size == 0
        if outcome == "failed":
            assert result.returncode == 23


@pytest.mark.parametrize("field", ["CFBundleExecutable", "CFBundleIconFile"])
def test_bundle_validation_rejects_missing_resources(tmp_path: Path, field: str) -> None:
    bundle = make_bundle(tmp_path)
    contents = bundle / "Contents"
    with (contents / "Info.plist").open("rb") as handle:
        info = plistlib.load(handle)
    directory = "MacOS" if field == "CFBundleExecutable" else "Resources"
    (contents / directory / info[field]).unlink()
    with pytest.raises(SMOKE["SmokeFailure"]):
        SMOKE["validate_distribution"](bundle, "macos")


@pytest.mark.parametrize("value", ["../outside", "/outside", ""])
def test_bundle_validation_rejects_unsafe_executable(tmp_path: Path, value: str) -> None:
    bundle = make_bundle(tmp_path)
    path = bundle / "Contents" / "Info.plist"
    with path.open("rb") as handle:
        info = plistlib.load(handle)
    info["CFBundleExecutable"] = value
    with path.open("wb") as handle:
        plistlib.dump(info, handle)
    with pytest.raises(SMOKE["SmokeFailure"]):
        SMOKE["validate_distribution"](bundle, "macos")
