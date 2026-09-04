# Packaging and release validation

[English](PACKAGING.md) | [Simplified Chinese](PACKAGING.zh-CN.md)

## Artifacts

| Platform | Artifact | Interfaces | GUI dependency |
| --- | --- | --- | --- |
| Linux x86_64 | Headless `tar.gz` | TUI, CLI | Excludes PySide6 |
| Linux x86_64 | GUI `tar.gz` | GUI, TUI, CLI | Includes required Qt plugins |
| Windows x64 | ZIP | GUI, TUI, CLI | Included |
| Python | Wheel | Platform-dependent | Linux uses optional `gui` extra |

Portable archives contain one executable, documentation, and a colocated editable `config.toml`. Each wheel, executable, and archive must not exceed 256 MB.

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

```bash
uv sync --frozen --extra gui --group dev
PYTHON=.venv/bin/python ./packaging/linux/build.sh
```

Outputs:

```text
dist/linux/MDHelper-<version>-Linux-x86_64.tar.gz
dist/linux/MDHelper-<version>-Linux-x86_64-GUI.tar.gz
```

The build audits payloads and size, extracts each archive, and checks version, TUI startup, headless
fallback, configuration, resources, a complete analysis with all export formats, and offscreen GUI
startup where applicable.

## Windows

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".venv-windows"
uv sync --frozen --group dev
.\packaging\windows\build.ps1 `
  -Python ".venv-windows\Scripts\python.exe" `
  -SmokeRequest "packaging\smoke\request.json"
```

The output is `dist/windows/MDHelper-<version>-Windows-x64.zip`. The build extracts the ZIP and checks
its root layout, all interface modes, colocated configuration, packaged resources, and a complete
analysis with all export formats. Keep `config.toml` beside `mdhelper.exe`. `--settings` and
`MDHELPER_CONFIG` override it.

Release gates pass only after the target-platform workflow completes; file presence is not a test
result.

## Automation

The `Quality` workflow runs for pull requests, pushes to `main`, and manual dispatches. Its Linux
and Windows jobs install the locked environment, validate version metadata, run Ruff, mypy, and the
complete test suite, then exercise the platform-specific startup path. The Linux job also builds,
audits, and installs the wheel in a clean environment.

Configure the default branch to require these checks before merging:

- `Quality / Linux`
- `Quality / Windows`

The Linux and Windows release-candidate workflows remain manually dispatchable. They also expose
reusable workflow entry points so the tag workflow can run the exact same target-platform builds.
Each candidate build runs source validation and the packaged-application smoke tests before its
artifacts are uploaded. Dependency and workflow action updates are grouped into weekly pull
requests by Dependabot and still pass through the normal quality gates.

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

The `Release` workflow rejects mismatched tags, builds the wheel and all three portable archives,
and waits for both target-platform jobs. Only its final job receives `contents: write`; it downloads
the validated artifacts, creates `SHA256SUMS`, and publishes the GitHub Release with generated
notes. Do not create or move a release tag until the corresponding commit has passed the required
checks.
