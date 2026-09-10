# Packaging and releases

[English](PACKAGING.md) | [简体中文](PACKAGING.zh-CN.md)

## Artifacts

| Platform | Output under `dist/` | Interfaces |
| --- | --- | --- |
| Linux x86_64 | `linux/MDHelper-<version>-Linux-x86_64.tar.gz` | TUI, CLI |
| Linux x86_64 | `linux/MDHelper-<version>-Linux-x86_64-GUI.tar.gz` | GUI, TUI, CLI |
| Windows x64 | `windows/MDHelper-<version>-Windows-x64.zip` | GUI, TUI, CLI |
| macOS arm64 | `macos/MDHelper-<version>-macOS-arm64.dmg` | GUI, TUI, CLI |
| Python | `mdhelper-<version>-py3-none-any.whl` | Linux GUI requires the `gui` extra |

Each wheel, executable, archive, and disk image is limited to 256 MB. Linux/Windows archives contain one executable, documentation, and editable `config.toml`. macOS distributes a complete `.app` and uses external user settings. See [Configuration](CONFIGURATION.md) for overrides. Build on the native target with Python 3.12+ and `uv`; cross-builds are unsupported.

## Wheel

```bash
uv sync --frozen --group dev
uv run python packaging/clean_build.py
uv build
wheel="dist/mdhelper-$(uv run python packaging/check_release.py)-py3-none-any.whl"
uv run python packaging/verify_wheel.py "$wheel"
```

Always clean `build` first. CI also installs the audited wheel in a fresh environment and checks entry points. macOS and Windows include PySide6 by default; Linux users install the `gui` extra.

## Linux

```bash
bash packaging/posix/install-deps.sh
uv sync --frozen --extra gui --group dev
PYTHON=.venv/bin/python bash packaging/posix/build.sh linux
```

This creates both headless and GUI archives. The installer uses APT and `sudo`; other distributions need equivalent XCB/XKB and graphics libraries. The Python extra and offscreen Qt do not replace these system dependencies, which are also needed for source/wheel GUI installations.

## Windows

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".venv-windows"
uv sync --frozen --group dev
.\packaging\windows\build.ps1 -Python ".venv-windows\Scripts\python.exe"
```

Keep `config.toml` beside `mdhelper.exe` when extracting the ZIP.

## macOS arm64

Requires Apple Silicon, native arm64 Python, and Xcode command-line tools:

```bash
uv sync --frozen --group dev
PYTHON=.venv/bin/python bash packaging/posix/build.sh macos
```

Open the DMG, drag `MDHelper.app` into Applications, eject the image, and launch from Finder. Copy the whole app, not just its launcher. The PyInstaller onedir bundle installs libraries in `Contents/Frameworks`; it does not unpack dependencies on each launch. The audit rejects embedded onefile dependencies and checks both expanded Qt plugins and embedded Python modules. Documents and examples are in `Contents/Resources`; settings are in `~/.config/mdhelper/config.toml`, outside the signed bundle.

Terminal entry points:

```bash
/Applications/MDHelper.app/Contents/MacOS/mdhelper tui
/Applications/MDHelper.app/Contents/MacOS/mdhelper cli --help
```

The app is ad-hoc signed, not Developer ID signed or notarized. If Gatekeeper blocks it, first verify the DMG against the published `SHA256SUMS`. Only for a trusted copy installed in Applications:

```bash
xattr -dr com.apple.quarantine /Applications/MDHelper.app
codesign --verify --deep --strict --verbose=2 /Applications/MDHelper.app
```

Removing quarantine does not sign the app. Do not disable Gatekeeper globally or re-sign an unmodified release. External tools launched in Terminal may require Automation permission.

## Automation

`Quality` runs locked-environment checks, lint/types, tests, native package builds, and runtime smoke tests on Linux, Windows, and macOS arm64. Require all three jobs before merging. [Development commands](ARCHITECTURE.md#development-checks) are documented separately.

To include runtime smoke tests in a local build, set `SMOKE_REQUEST=packaging/smoke/request.json` on POSIX or pass `-SmokeRequest "packaging\smoke\request.json"` on Windows. These exercise installed layout, configuration, resources, CLI/TUI/GUI, and analysis exports. macOS additionally checks signatures, a copied app after DMG ejection, native Cocoa, and Launch Services.

Manual/tag builds audit metadata, payloads, licenses, signatures, and size without repeating commit tests. A successful build is not a substitute for green Quality checks.

## Publishing a release

Keep `pyproject.toml` and `src/mdhelper/version.py` synchronized; refresh and commit `uv.lock` after metadata/dependency changes. Once the target commit has passed all Quality jobs:

```bash
version=$(uv run python packaging/check_release.py)
git tag -a "v${version}" -m "MDHelper ${version}"
git push origin "v${version}"
```

`Release` rejects mismatched tags, waits for all platform artifacts, generates `SHA256SUMS`, and publishes the GitHub release. Do not move an existing release tag.
