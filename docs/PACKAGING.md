# Packaging and release validation

[English](PACKAGING.md) | [Simplified Chinese](PACKAGING.zh-CN.md)

MDHelper release packages are classified by platform, and every platform package is a portable
archive:

- Linux x86_64: a `tar.gz` containing one standalone `mdhelper` executable,
  documentation, and an editable colocated `config.toml`. The executable bundles the TUI and CLI
  and deliberately excludes PySide6.
- Windows x64: a ZIP containing one standalone `mdhelper.exe`, documentation, and an
  editable colocated `config.toml`. It does not require installation or administrator access and
  is the only Windows artifact.

The Python wheel is a separate source-managed installation path containing the unified `mdhelper`
launcher. PySide6 is excluded unless the optional `gui` extra is explicitly requested.

Every wheel, standalone executable, and portable archive has a strict 256 MB size limit.
Packaging fails before publication if any artifact exceeds it. Frozen payload audits also
reject duplicate test/build runtimes, unused analysis modules, and platform-inappropriate Qt
components.

## Linux build

Build on Linux x86_64 from the locked core environment:

```bash
uv sync --frozen --group dev
PYTHON=.venv/bin/python ./packaging/linux/build.sh
```

The release archive is written to
`dist/linux/MDHelper-0.1.0-Linux-x86_64.tar.gz`. The build rejects PySide6 and test/build tooling
inside the frozen payload, verifies the executable and archive independently against the 256 MB
limit, extracts the completed archive, and runs that extracted application. The smoke test
exercises `--version`, explicit TUI startup, argument-free TUI fallback, portable configuration,
and a CLI resource command. After extraction:

```bash
./mdhelper
./mdhelper tui
./mdhelper cli --help
```

No Python installation is required. This headless 0.1.0 Linux release guarantees TUI and CLI;
the Windows build remains the GUI release target.

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
and builds the wheel. The Linux release workflow additionally freezes and smoke-tests the
standalone TUI/CLI archive on Ubuntu 22.04. The built wheel is also inspected to ensure that only
the package entry points and version module remain at the `mdhelper/` root; stale compatibility
shells fail the release gate.

Workflow definitions provide repeatable gates; a release gate is satisfied only by a successful run on the target platform, not merely by the presence of these files.
