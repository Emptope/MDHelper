# 打包与发布验证

[English](PACKAGING.md) | [简体中文](PACKAGING.zh-CN.md)

## 产物

| 平台 | 产物 | 界面 | GUI 依赖 |
| --- | --- | --- | --- |
| Linux x86_64 | 无头版 `tar.gz` | TUI、CLI | 排除 PySide6 |
| Linux x86_64 | GUI 版 `tar.gz` | GUI、TUI、CLI | 包含所需 Qt plugin |
| Windows x64 | ZIP | GUI、TUI、CLI | 包含 |
| macOS arm64 | 候选版 `tar.gz` | GUI、TUI、CLI | 包含；尚需原生验证 |
| Python | Wheel | 取决于平台 | Linux 使用可选 `gui` extra |

便携归档包含一个 executable、文档和同目录可编辑 `config.toml`。每个 wheel、executable 和 archive 不得超过 256 MB。

## Wheel

使用 Python 3.12 或更高版本及锁定的 `uv` 版本构建和审计：

```bash
uv sync --frozen --group dev
uv run python packaging/clean_build.py
uv build
wheel="dist/mdhelper-$(uv run python packaging/check_release.py)-py3-none-any.whl"
uv run python packaging/verify_wheel.py "$wheel"
```

每次构建前必须先删除仓库的 `build` 目录。随后构建会先创建 sdist，再从该干净源码归档构建
wheel。审计比较 package 与源码中的模块和资源，并检查大小。在干净环境中测试 wheel：

```bash
wheel="dist/mdhelper-$(uv run python packaging/check_release.py)-py3-none-any.whl"
uv venv --python 3.12 /tmp/mdhelper-wheel-test
uv pip install --python /tmp/mdhelper-wheel-test/bin/python "$wheel"
/tmp/mdhelper-wheel-test/bin/mdhelper --version
/tmp/mdhelper-wheel-test/bin/mdhelper cli --help
```

Linux GUI 安装增加 extra：

```bash
wheel="dist/mdhelper-$(uv run python packaging/check_release.py)-py3-none-any.whl"
uv pip install --python /tmp/mdhelper-wheel-test/bin/python \
  "${wheel}[gui]"
QT_QPA_PLATFORM=offscreen /tmp/mdhelper-wheel-test/bin/mdhelper gui --smoke-test
```

产物版本来自 `pyproject.toml`。

## Linux

```bash
uv sync --frozen --extra gui --group dev
PYTHON=.venv/bin/python ./packaging/linux/build.sh
```

产物为：

```text
dist/linux/MDHelper-<version>-Linux-x86_64.tar.gz
dist/linux/MDHelper-<version>-Linux-x86_64-GUI.tar.gz
```

默认构建只审计内容和大小，不运行测试。commit 检查通过设置
`SMOKE_REQUEST=packaging/smoke/request.json` 启用解压和运行时测试，检查版本、TUI 启动、
headless fallback、配置、资源、包含全部导出格式的完整分析，以及适用时的 offscreen GUI 启动。

## Windows

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".venv-windows"
uv sync --frozen --group dev
.\packaging\windows\build.ps1 -Python ".venv-windows\Scripts\python.exe"
```

产物为 `dist/windows/MDHelper-<version>-Windows-x64.zip`。默认构建只审计可执行文件和归档，
不运行测试。commit 检查追加 `-SmokeRequest "packaging\smoke\request.json"` 后才解压 ZIP，
检查归档根布局、全部界面模式、同目录配置、package 资源，以及包含全部导出格式的完整分析。
`config.toml` 必须与 `mdhelper.exe` 同目录。`--settings` 和 `MDHELPER_CONFIG` 可覆盖该路径。

测试属于 commit 检查，不在 release 构建中重复执行。构建成功不代表测试通过；只发布已通过
目标平台 `Quality` 检查的 commit。

## macOS arm64

使用 Apple Silicon Mac、原生 arm64 Python 3.12 和 Xcode 命令行工具构建。
构建脚本拒绝 Intel 主机及转译运行的 x86_64 Python，不支持交叉构建。

```bash
uv sync --frozen --group dev
PYTHON=.venv/bin/python bash packaging/macos/build.sh
```

产物为 `dist/macos/MDHelper-<version>-macOS-arm64.tar.gz`。解压后保留与 `mdhelper`
同目录的 `config.toml`，在 Terminal 中执行 `./mdhelper`。macOS 默认安装 PySide6，
源码与 wheel 安装无需额外指定 `gui` extra。

Linux 与 macOS 入口共享 `packaging/posix/`，每个变体构建前均完整清理 `build`。
构建审计 arm64 可执行文件、临时代码签名、Qt 内容和 256 MB 体积限制。commit 检查设置
`SMOKE_REQUEST=packaging/smoke/request.json`，测试解压布局、CLI/TUI、offscreen 与 Cocoa GUI、
同目录配置、资源，以及分析和导出结果。
外部交互工具通过 Terminal 启动，分别传递经 shell 引用的参数、工作目录与过滤后的环境；
系统可能要求授予自动化权限。

候选版使用 ad-hoc 签名，尚无 Developer ID 签名和公证。Gatekeeper 可能阻止下载的程序；
请先核对 `SHA256SUMS`，再对可信程序使用系统提供的单应用放行方式，不要全局关闭 Gatekeeper。
目前仍待原生 macOS 构建、Cocoa 及交互 Terminal 验证；Linux/Windows 测试和平台模拟测试
不代表 macOS 已满足发布条件。标记支持完成前，需要记录 commit、原生 arm64 Python 与 macOS
版本、`Quality` 运行链接、归档哈希，以及从含空格目录启动外部工具的结果；确认授予自动化权限后
Terminal 正确保留参数和工作目录。

## 自动化流程

`Quality` 工作流在 pull request、推送到 `main` 和手动触发时运行。Linux、Windows 与
macOS arm64 job 均会安装锁定环境、校验版本元数据、运行 Ruff、mypy 和完整测试集，再构建原生
归档并运行 smoke test、检查平台对应的启动路径。Linux 与 macOS job 还会构建和审计 wheel，
并在干净环境中安装验证。Linux 测试使用四进程，Windows 保持串行；所有源码和运行时测试均由
这些 commit 检查负责。

对默认分支配置以下合并前必须通过的检查：

- `Quality / Linux`
- `Quality / Windows`
- `Quality / macOS arm64`

Linux、Windows 与 macOS 发布候选工作流仍可手动触发，同时暴露可复用工作流入口，供标签发布调用
同一套目标平台构建。候选和标签 release 只校验版本、构建、审计内容、许可、签名和大小，再上传或
发布产物；不重复执行 lint、类型检查、单元测试、依赖审计或运行时 smoke test。Dependabot 每周将
依赖和工作流 action 更新各自分组为 pull request，更新仍需通过 commit 质量门禁。

## 发布正式版本

保持 `pyproject.toml` 与 `src/mdhelper/version.py` 的版本一致。修改依赖或项目元数据后，需更新
`uv.lock` 并与改动一起提交。创建标签前运行：

```bash
uv sync --frozen --group dev
uv run python packaging/check_release.py
uv run ruff check conftest.py packaging src tests
uv run mypy src packaging/check_release.py packaging/clean_build.py packaging/smoke_check.py
uv run pytest -q
```

确认 `main` 上的必需检查全部通过后，创建并推送与元数据完全一致的版本标签：

```bash
version=$(uv run python packaging/check_release.py)
git tag -a "v${version}" -m "MDHelper ${version}"
git push origin "v${version}"
```

`Release` 工作流会拒绝不匹配的标签，构建 wheel 和四个便携式归档，并等待三个目标平台 job
完成。只有最后的 job 获得 `contents: write` 权限；它下载已审计的产物、生成 `SHA256SUMS`，
并创建带自动生成说明的 GitHub Release。在对应 commit 通过必需检查前，不要创建或移动发布标签。
