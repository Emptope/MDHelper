# 打包与发布

[English](PACKAGING.md) | [简体中文](PACKAGING.zh-CN.md)

## 产物

| 平台 | `dist/` 下的产物 | 界面 |
| --- | --- | --- |
| Linux x86_64 | `linux/MDHelper-<version>-Linux-x86_64.tar.gz` | TUI、CLI |
| Linux x86_64 | `linux/MDHelper-<version>-Linux-x86_64-GUI.tar.gz` | GUI、TUI、CLI |
| Windows x64 | `windows/MDHelper-<version>-Windows-x64.zip` | GUI、TUI、CLI |
| macOS arm64 | `macos/MDHelper-<version>-macOS-arm64.dmg` | GUI、TUI、CLI |
| Python | `mdhelper-<version>-py3-none-any.whl` | Linux GUI 需安装 `gui` extra |

每个 wheel、可执行文件、归档和磁盘映像限制为 256 MB。Linux/Windows 归档包含单一可执行文件、文档与可编辑的 `config.toml`；macOS 分发完整 `.app` 并使用外部用户配置。覆盖规则见[配置](CONFIGURATION.zh-CN.md)。在目标平台使用 Python 3.12+ 和 `uv` 原生构建，不支持交叉构建。

## Wheel

```bash
uv sync --frozen --group dev
uv run python packaging/clean_build.py
uv build
wheel="dist/mdhelper-$(uv run python packaging/check_release.py)-py3-none-any.whl"
uv run python packaging/verify_wheel.py "$wheel"
```

必须先清理 `build`。CI 还会在全新环境中安装已审计 wheel 并检查入口。macOS 和 Windows 默认包含 PySide6；Linux GUI 用户需安装 `gui` extra。

## Linux

```bash
bash packaging/posix/install-deps.sh
uv sync --frozen --extra gui --group dev
PYTHON=.venv/bin/python bash packaging/posix/build.sh linux
```

同时生成无 GUI 和 GUI 归档。依赖安装器使用 APT 与 `sudo`，其他发行版需安装等效的 XCB/XKB 和图形库。Python extra 与 offscreen Qt 不能替代这些系统依赖，源码和 wheel 的 GUI 安装也需要它们。

## Windows

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".venv-windows"
uv sync --frozen --group dev
.\packaging\windows\build.ps1 -Python ".venv-windows\Scripts\python.exe"
```

解压后将 `config.toml` 保留在 `mdhelper.exe` 同目录。

## macOS arm64

需要 Apple Silicon、原生 arm64 Python 和 Xcode 命令行工具：

```bash
uv sync --frozen --group dev
PYTHON=.venv/bin/python bash packaging/posix/build.sh macos
```

打开 DMG，将 `MDHelper.app` 拖入 Applications，弹出映像后从 Finder 启动。必须复制完整应用，不能只复制启动器。PyInstaller onedir 应用包将依赖预展开到 `Contents/Frameworks`，不会在每次启动时重新解压。审计会拒绝内嵌 onefile 依赖，同时检查展开的 Qt 插件和内嵌 Python 模块。文档与示例在 `Contents/Resources`；配置位于签名包外的`~/.config/mdhelper/config.toml`。

终端入口：

```bash
/Applications/MDHelper.app/Contents/MacOS/mdhelper tui
/Applications/MDHelper.app/Contents/MacOS/mdhelper cli --help
```

应用采用 ad-hoc 签名，不是 Developer ID 签名，也未公证。若 Gatekeeper 阻止启动，先核对 DMG 与发布的 `SHA256SUMS`。仅对已安装到 Applications 且确认可信的副本执行：

```bash
xattr -dr com.apple.quarantine /Applications/MDHelper.app
codesign --verify --deep --strict --verbose=2 /Applications/MDHelper.app
```

移除隔离属性不会签名应用。不要全局关闭 Gatekeeper，也无需重新签名未修改的发布包。通过 Terminal 启动外部工具可能需要 Automation 权限。

## 自动化流程

`Quality` 在 Linux、Windows 和 macOS arm64 上执行锁定环境检查、lint/类型检查、测试、原生打包和运行时 smoke test。合并前应要求三个 job 全部通过。[开发命令](ARCHITECTURE.zh-CN.md#开发检查) 单独维护。

本地构建如需运行 smoke test，POSIX 设置 `SMOKE_REQUEST=packaging/smoke/request.json`，Windows 传入 `-SmokeRequest "packaging\smoke\request.json"`。检查覆盖安装布局、配置、资源、CLI/TUI/GUI 和分析导出；macOS 另检查签名、弹出 DMG 后的应用副本、原生 Cocoa 与 Launch Services。

手动和 tag 构建审计元数据、payload、许可证、签名及大小，不重复 commit 测试。构建成功不能替代 Quality 检查通过。

## 发布正式版本

保持 `pyproject.toml` 与 `src/mdhelper/version.py` 版本一致，元数据或依赖变化后更新并提交 `uv.lock`。目标 commit 通过全部 Quality job 后：

```bash
version=$(uv run python packaging/check_release.py)
git tag -a "v${version}" -m "MDHelper ${version}"
git push origin "v${version}"
```

`Release` 拒绝不匹配的 tag，等待所有平台产物，生成 `SHA256SUMS` 并发布 GitHub Release。不要移动已发布的 tag。
