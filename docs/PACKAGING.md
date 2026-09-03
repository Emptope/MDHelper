# Packaging and release validation

[English](PACKAGING.md) | [Simplified Chinese](PACKAGING.zh-CN.md)

## Artifacts

| Platform | Artifact | Interfaces | GUI dependency |
| --- | --- | --- | --- |
| Linux x86_64 | Headless `tar.gz` | TUI, CLI | Excludes PySide6 |
| Linux x86_64 | GUI `tar.gz` | GUI, TUI, CLI | Includes required Qt plugins |
| Windows x64 | ZIP | GUI, TUI, CLI | Included |
| Python | Wheel | Platform-dependent | Linux uses optional `gui` extra |

Portable archives contain one executable, documentation, and a colocated editable `config.toml`.
They do not include GROMACS. Each wheel, executable, and archive must not exceed 256 MB.

## Wheel

Build and audit with Python 3.12 or newer and the locked `uv` version:

```bash
uv sync --frozen --group dev
uv build --wheel
uv run python packaging/verify_wheel.py dist/mdhelper-0.1.0-py3-none-any.whl
```

The audit compares packaged modules and resources with the source tree and checks size. Test the
wheel in a clean environment:

```bash
uv venv --python 3.12 /tmp/mdhelper-wheel-test
uv pip install --python /tmp/mdhelper-wheel-test/bin/python \
  ./dist/mdhelper-0.1.0-py3-none-any.whl
/tmp/mdhelper-wheel-test/bin/mdhelper --version
/tmp/mdhelper-wheel-test/bin/mdhelper cli --help
```

Linux GUI installation adds the extra:

```bash
uv pip install --python /tmp/mdhelper-wheel-test/bin/python \
  "./dist/mdhelper-0.1.0-py3-none-any.whl[gui]"
QT_QPA_PLATFORM=offscreen /tmp/mdhelper-wheel-test/bin/mdhelper gui --smoke-test
```

The artifact version comes from `pyproject.toml`.

## Linux

```bash
uv sync --frozen --extra gui --group dev
PYTHON=.venv/bin/python ./packaging/linux/build.sh
```

Outputs:

```text
dist/linux/MDHelper-0.1.0-Linux-x86_64.tar.gz
dist/linux/MDHelper-0.1.0-Linux-x86_64-GUI.tar.gz
```

The build audits payloads and size, extracts each archive, and checks version, TUI startup, headless
fallback, configuration, resources, and offscreen GUI startup where applicable.

## Windows

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".venv-windows"
uv sync --frozen --group dev
.\packaging\windows\build.ps1 -Python ".venv-windows\Scripts\python.exe"
```

The output is `dist/windows/MDHelper-0.1.0-Windows-x64.zip`. The build extracts the ZIP and checks
all interface modes, colocated configuration, and packaged resources. Keep `config.toml` beside
`mdhelper.exe`. `--settings` and `MDHELPER_CONFIG` override it.

Release gates pass only after the target-platform workflow completes; file presence is not a test
result.
