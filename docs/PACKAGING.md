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

Each wheel, executable, archive, and disk image is limited to 256 MB. Linux archives contain one executable; Windows archives contain a self-contained executable and a small native terminal forwarder. Both include documentation and editable `config.toml`. macOS distributes a complete `.app` and uses external user settings. See [Configuration](CONFIGURATION.md) for overrides. Build on the native target with Python 3.12+ and `uv`; cross-builds are unsupported.

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

Building also requires an x64 C compiler (Visual Studio C++ build tools or MinGW-w64). The build script detects the installed toolchain and compiles the terminal forwarder with a static runtime.

- `mdhelper.exe`: self-contained GUI application using the Windows GUI PE subsystem (`console=False`). Python, Qt, and application modules are compressed inside this file.
- `mdhelper.com`: small native console forwarder; defaults to TUI. It starts the sibling `.exe`, forwards arguments and streams, and returns its exit status. It contains no second Python or Qt payload.

Keep both files and `config.toml` together. There is no exposed library directory. The onefile runtime expands into a temporary directory and is cleaned up on exit; both bootloader processes use the GUI subsystem, so neither creates a startup console. Terminal modes attach to the forwarder's console and preserve redirected handles before attachment. The forwarder preserves shell waiting and exit status, and starts an independent onefile runtime so a TUI opened from the GUI survives GUI shutdown. Use `mdhelper.com tui` or `mdhelper.com cli <command>` for terminal work. With the default Windows `PATHEXT` ordering, `mdhelper tui` also selects the `.com` entry; use the explicit extension if that ordering was customized. Background detection, analysis, and process-tree cancellation use `CREATE_NO_WINDOW`. GUI-to-TUI and interactive external tools use `CREATE_NEW_CONSOLE`, so the system default terminal can host them; MDHelper does not force `wt.exe` or change that default.

The Windows smoke script validates both PE subsystems and the extracted layout, then runs `launch_check.py` on the native desktop. It checks default/explicit GUI launch for visible application windows and absence of console ownership in both onefile processes, plus terminal allocation, piped input, output, independent runtime ownership, quoted paths, file redirection, and exit status. Offscreen GUI, CLI configuration, and analysis exports are also checked.

For manual checks with Windows Console Host and Windows Terminal selected as the default terminal:

1. Double-click `mdhelper.exe`, then launch `mdhelper.exe gui` from an existing terminal. The GUI should open without an extra terminal window; the existing terminal must remain usable.
2. Let startup detection finish, run integration detection and an analysis, then cancel an analysis. No background command should open a console.
3. Run `mdhelper.com tui` and `mdhelper.com cli --help` from PowerShell inside Windows Terminal. Check keyboard input, shell waiting until exit, exit status, and redirected CLI output (`mdhelper.com cli config show > config.json`).
4. Open TUI from the GUI and an interactive `gmx make_ndx` session. Each should receive its requested terminal and accept input.

Do not use the GUI executable for shell automation: Windows shells do not guarantee waiting for GUI-subsystem applications. Source and wheel entry points are unchanged.

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
