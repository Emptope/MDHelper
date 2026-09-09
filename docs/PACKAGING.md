# Packaging and release validation

[English](PACKAGING.md) | [简体中文](PACKAGING.zh-CN.md)

## Artifacts

| Platform | Artifact | Interfaces | GUI dependency |
| --- | --- | --- | --- |
| Linux x86_64 | Headless `tar.gz` | TUI, CLI | Excludes PySide6 |
| Linux x86_64 | GUI `tar.gz` | GUI, TUI, CLI | Includes required Qt plugins |
| Windows x64 | ZIP | GUI, TUI, CLI | Included |
| macOS arm64 | DMG with `.app` | GUI, TUI, CLI | Included |
| Python | Wheel | Platform-dependent | Linux uses optional `gui` extra |

Linux and Windows portable archives contain one executable, documentation, and a colocated editable `config.toml`. The macOS DMG contains `MDHelper.app` and an Applications shortcut. Each wheel, executable, archive, and disk image must not exceed 256 MB.

## Wheel

Build and audit with Python 3.12 or newer and the locked `uv` version:

```bash
uv sync --frozen --group dev
uv run python packaging/clean_build.py
uv build
wheel="dist/mdhelper-$(uv run python packaging/check_release.py)-py3-none-any.whl"
uv run python packaging/verify_wheel.py "$wheel"
```

Every build must remove the repository `build` directory first. The build then creates an sdist and
builds the wheel from that clean source archive. The audit compares packaged modules and resources
with the source tree and checks size. Test the wheel in a clean environment:

```bash
wheel="dist/mdhelper-$(uv run python packaging/check_release.py)-py3-none-any.whl"
uv venv --python 3.12 /tmp/mdhelper-wheel-test
uv pip install --python /tmp/mdhelper-wheel-test/bin/python "$wheel"
/tmp/mdhelper-wheel-test/bin/mdhelper --version
/tmp/mdhelper-wheel-test/bin/mdhelper cli --help
```

Linux GUI installation adds the extra:

```bash
wheel="dist/mdhelper-$(uv run python packaging/check_release.py)-py3-none-any.whl"
uv pip install --python /tmp/mdhelper-wheel-test/bin/python \
  "${wheel}[gui]"
QT_QPA_PLATFORM=offscreen /tmp/mdhelper-wheel-test/bin/mdhelper gui --smoke-test
```

The artifact version comes from `pyproject.toml`.

## Linux

On Ubuntu/Debian, install the system GUI libraries before freezing the application:

```bash
bash packaging/posix/install-deps.sh
uv sync --frozen --extra gui --group dev
PYTHON=.venv/bin/python bash packaging/posix/build.sh linux
```

Both Linux CI workflows use the same dependency installer. The XCB and XKB runtime libraries
must be available when freezing so the GUI payload can include Qt's X11 dependencies.
Installing the Python `gui` extra or testing with `QT_QPA_PLATFORM=offscreen` does not supply or
validate those system libraries. Source and wheel GUI installs need them on the target system too.
The installer uses `sudo` and APT; other distributions need equivalent runtime packages.

Outputs:

```text
dist/linux/MDHelper-<version>-Linux-x86_64.tar.gz
dist/linux/MDHelper-<version>-Linux-x86_64-GUI.tar.gz
```

The default build audits payloads and size without running tests. Commit checks opt into archive
extraction and runtime tests with `SMOKE_REQUEST=packaging/smoke/request.json`. These check version,
TUI startup, headless fallback, configuration, resources, a complete analysis with all export
formats, and offscreen GUI startup where applicable.

## Windows

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".venv-windows"
uv sync --frozen --group dev
.\packaging\windows\build.ps1 -Python ".venv-windows\Scripts\python.exe"
```

The output is `dist/windows/MDHelper-<version>-Windows-x64.zip`. The default build audits the
executable and archive without running tests. Commit checks add
`-SmokeRequest "packaging\smoke\request.json"` to extract the ZIP and test its root layout, all
interface modes, colocated configuration, packaged resources, and a complete analysis with all
export formats. Keep `config.toml` beside `mdhelper.exe`. `--settings` and `MDHELPER_CONFIG` override it.

Tests belong to commit checks, not release builds. A successful release build is not a test result;
release only a commit whose target-platform `Quality` checks have passed.

## macOS arm64

Build on an Apple Silicon Mac with native arm64 Python 3.12 and the Xcode command-line
tools. Intel hosts and translated x86_64 Python are rejected; this is not a cross-build.

```bash
uv sync --frozen --group dev
PYTHON=.venv/bin/python bash packaging/posix/build.sh macos
```

Output: `dist/macos/MDHelper-<version>-macOS-arm64.dmg`. Open the DMG, drag
`MDHelper.app` to Applications, eject the image, and launch the app from Finder.
For terminal interfaces, run `/Applications/MDHelper.app/Contents/MacOS/mdhelper tui`
or `/Applications/MDHelper.app/Contents/MacOS/mdhelper cli --help`.
Settings are saved to `~/.config/mdhelper/config.toml`, outside the
signed bundle. `--settings` and `MDHELPER_CONFIG` still override the default.
Documentation, schemas, licenses, and the example configuration are in `Contents/Resources`.
PySide6 is a default dependency on macOS, so source and wheel installs need no `gui` extra.

Linux and macOS use `packaging/posix/build.sh` with an explicit platform argument.
Each variant removes `build` before freezing. The build audits the arm64 executable,
ad-hoc application signature, Qt payload, DMG integrity, and 256 MB size limit.
Commit checks set `SMOKE_REQUEST=packaging/smoke/request.json` to mount the DMG read-only,
copy the app to a directory containing spaces, eject the image, and check the installed
signature, CLI/TUI, offscreen and Cocoa GUI, user configuration, resources, and analysis/export
results. The installed bundle is also launched through Launch Services.
Interactive external tools open in Terminal with separately quoted arguments,
working directory, and a filtered environment; macOS may request Automation permission.

The application is ad-hoc signed, not Developer ID signed or notarized. Gatekeeper may
block downloaded applications. First verify the DMG's SHA-256 against the published
`SHA256SUMS`. For a trusted application already copied to Applications, remove its
quarantine attribute and verify the existing signature:

```bash
xattr -dr com.apple.quarantine /Applications/MDHelper.app
codesign --verify --deep --strict --verbose=2 /Applications/MDHelper.app
```

`xattr` removes download quarantine; it does not sign the app. The released app is already
ad-hoc signed. Only when intentionally re-signing a locally modified, trusted copy, run:

```bash
codesign --force --sign - /Applications/MDHelper.app
codesign --verify --deep --strict --verbose=2 /Applications/MDHelper.app
```

Local ad-hoc signing does not provide Developer ID identity or notarization. These commands
apply only to this app; do not disable Gatekeeper globally.

## Automation

The `Quality` workflow runs for pull requests, pushes to `main`, and manual dispatches. Its Linux,
Windows, and macOS arm64 jobs install the locked environment, validate version metadata, run Ruff,
mypy, and the complete test suite, then build and smoke-test the native packages and exercise the
platform-specific startup path. Linux and macOS also build, audit, and install the wheel in a clean
environment. Linux tests use four workers; Windows tests remain serial. These commit checks own all
source and runtime tests.

Configure the default branch to require these checks before merging:

- `Quality / Linux`
- `Quality / Windows`
- `Quality / macOS arm64`

The Linux, Windows, and macOS packaging workflows remain manually dispatchable. They also expose
reusable workflow entry points so the tag workflow can run the exact same target-platform builds.
Manual and tag release builds only validate versions, build, audit payloads, licenses, signatures and
size, and upload or publish artifacts. They do not repeat lint, typing, unit tests, dependency audits,
or runtime smoke tests. Dependency and workflow action updates are grouped into weekly pull
requests by Dependabot and still pass through the commit quality gates.

## Publishing a release

Keep `pyproject.toml` and `src/mdhelper/version.py` on the same version. After changing either
dependency or project metadata, refresh `uv.lock` and commit it with the change. Before tagging,
run:

```bash
uv sync --frozen --group dev
uv run python packaging/check_release.py
uv run ruff check conftest.py packaging src tests
uv run mypy src packaging/check_release.py packaging/clean_build.py packaging/smoke_check.py
uv run pytest -q
```

Once the required checks are green on `main`, create and push a version tag that exactly matches
the metadata:

```bash
version=$(uv run python packaging/check_release.py)
git tag -a "v${version}" -m "MDHelper ${version}"
git push origin "v${version}"
```

The `Release` workflow rejects mismatched tags, builds the wheel, three portable archives, and macOS DMG,
and waits for all three target-platform jobs. Only its final job receives `contents: write`; it downloads
the audited artifacts, creates `SHA256SUMS`, and publishes the GitHub Release with generated
notes. Do not create or move a release tag until the corresponding commit has passed the required
checks.
