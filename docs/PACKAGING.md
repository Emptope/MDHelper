# Packaging and release validation

[English](PACKAGING.md) | [Simplified Chinese](PACKAGING.zh-CN.md)

MDHelper release packages are classified by platform, and every platform package is a portable
archive:

- Linux x86_64 headless: a `tar.gz` containing one standalone `mdhelper` executable,
  documentation, and an editable colocated `config.toml`. The executable bundles the TUI and CLI
  and deliberately excludes PySide6.
- Linux x86_64 GUI: a second `tar.gz` with the same portable layout and all three interfaces. It
  bundles the supported Qt Widgets runtime and X11, Wayland, and offscreen platform plugins.
- Windows x64: a ZIP containing one standalone `mdhelper.exe`, documentation, and an
  editable colocated `config.toml`. It does not require installation or administrator access and
  is the only Windows artifact.

The Python wheel is a separate source-managed installation path containing the unified `mdhelper`
launcher. On Linux, PySide6 is excluded unless the optional `gui` extra is explicitly requested.
On Windows, the default installation includes PySide6 so the GUI works without an extra.

Every wheel, standalone executable, and portable archive has a strict 256 MB size limit.
Packaging fails before publication if any artifact exceeds it. Frozen payload audits also
reject duplicate test/build runtimes, unused analysis modules, and platform-inappropriate Qt
components.

## Python wheel

Build the wheel from the repository root with Python 3.12+ and `uv 0.12.6`, matching the quality
workflow:

```bash
uv sync --frozen --group dev
uv build --wheel
uv run python packaging/verify_wheel.py dist/mdhelper-0.1.0-py3-none-any.whl
```

`uv build --wheel` uses the isolated build backend declared in `pyproject.toml` and writes only the
wheel to `dist/`. The result is `dist/mdhelper-0.1.0-py3-none-any.whl`; it is platform-independent,
but its dependencies are resolved for the platform where it is installed. The repository audit
enforces the 256 MB limit, checks that every Python module matches `src/mdhelper`, rejects extra
package-root modules, and confirms that all source templates are present. Do not distribute a
wheel that has not passed this audit. The wheel also carries the schemas and bilingual user,
method, and validation documents declared in `pyproject.toml`; it does not bundle Python or
GROMACS.

The setuptools backend may reuse the generated `build/` directory. If the audit reports unexpected
modules after source files were renamed or deleted, remove only `build/`, then rebuild and rerun the
audit. This directory contains generated files and is not a release artifact.

Test the exact artifact in a clean virtual environment rather than the development environment.
On Linux, use:

```bash
uv venv --python 3.12 /tmp/mdhelper-wheel-test
uv pip install --python /tmp/mdhelper-wheel-test/bin/python \
  ./dist/mdhelper-0.1.0-py3-none-any.whl
/tmp/mdhelper-wheel-test/bin/mdhelper --version
/tmp/mdhelper-wheel-test/bin/mdhelper cli --help
```

On Windows PowerShell, use:

```powershell
$wheelTest = Join-Path $env:TEMP "mdhelper-wheel-test"
uv venv --python 3.12 $wheelTest
uv pip install --python "$wheelTest\Scripts\python.exe" `
  .\dist\mdhelper-0.1.0-py3-none-any.whl
& "$wheelTest\Scripts\mdhelper.exe" --version
& "$wheelTest\Scripts\mdhelper.exe" cli --help
```

A default Linux wheel installation provides the TUI and CLI. To install the optional Linux GUI,
use:

```bash
uv pip install --python /tmp/mdhelper-wheel-test/bin/python \
  "./dist/mdhelper-0.1.0-py3-none-any.whl[gui]"
QT_QPA_PLATFORM=offscreen /tmp/mdhelper-wheel-test/bin/mdhelper gui --smoke-test
```

The version in `pyproject.toml` determines the artifact name. When the project version changes,
use the newly generated filename in both the audit and installation commands.

## Linux build

Build on Linux x86_64 from the locked GUI development environment:

```bash
uv sync --frozen --extra gui --group dev
PYTHON=.venv/bin/python ./packaging/linux/build.sh
```

The two release archives are written to
`dist/linux/MDHelper-0.1.0-Linux-x86_64.tar.gz` and
`dist/linux/MDHelper-0.1.0-Linux-x86_64-GUI.tar.gz`. The headless build rejects PySide6; the GUI
build retains only the Qt modules and desktop plugins required by the application. Both reject
test/build tooling, verify the executable and archive independently against the 256 MB limit,
extract the completed archive, and run that extracted application. The smoke tests exercise
`--version`, explicit TUI startup, argument-free TUI fallback without a display, portable
configuration, and a CLI resource command. The GUI archive additionally starts Qt through the
offscreen platform plugin. After extracting the headless archive:

```bash
./mdhelper
./mdhelper tui
./mdhelper cli --help
```

No Python installation is required. This headless 0.1.0 Linux release guarantees TUI and CLI;
extract the GUI archive on a Linux desktop and run `./mdhelper` or `./mdhelper gui` to open the GUI.
The GUI archive also retains the TUI and CLI modes.

## Windows build

Build on Windows x64 from the locked development environment:

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".venv-windows"
uv sync --frozen --group dev
.\packaging\windows\build.ps1 `
  -Python ".venv-windows\Scripts\python.exe"
```

The Windows archive is written to
`dist/windows/MDHelper-0.1.0-Windows-x64.zip`. The build extracts that actual ZIP into a
temporary directory and fails unless all interface modes start, `config path` resolves to the
colocated `config.toml`, and the packaged resources are available. The archive contains the
runtime, core dependencies, method/validation documents,
configuration, and generated dependency/version/license inventory. It does not bundle or require
GROMACS.

After extraction, `config.toml` and `mdhelper.exe` must remain together.
Without arguments the application opens the GUI when available and otherwise falls back to TUI.
Use `mdhelper.exe gui`, `mdhelper.exe tui`, or `mdhelper.exe cli` to select a mode. GUI startup does
not keep a console window: the console launcher starts the GUI as an independent detached process
and exits. Explicit terminal modes remain connected to their launching shell or create a console
when needed. Every frozen application selects its colocated configuration automatically. An
explicit `--settings` CLI argument or `MDHELPER_CONFIG` environment variable still takes precedence.

## Linux validation

The quality workflow installs the locked core environment without the GUI extra, asserts that
PySide6 is absent, verifies automatic TUI fallback and the CLI without a display, executes tests,
and builds the wheel. The Linux release workflow installs the locked GUI extra, then freezes and
smoke-tests both standalone archives on Ubuntu 22.04. The built wheel is also inspected to ensure
that only the package entry points and version module remain at the `mdhelper/` root; stale
compatibility shells fail the release gate.

Workflow definitions provide repeatable gates; a release gate is satisfied only by a successful run on the target platform, not merely by the presence of these files.
