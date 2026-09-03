# 打包与发布验证

[English](PACKAGING.md) | [简体中文](PACKAGING.zh-CN.md)

## 产物

| 平台 | 产物 | 界面 | GUI 依赖 |
| --- | --- | --- | --- |
| Linux x86_64 | 无头版 `tar.gz` | TUI、CLI | 排除 PySide6 |
| Linux x86_64 | GUI 版 `tar.gz` | GUI、TUI、CLI | 包含所需 Qt plugin |
| Windows x64 | ZIP | GUI、TUI、CLI | 包含 |
| Python | Wheel | 取决于平台 | Linux 使用可选 `gui` extra |

便携归档包含一个 executable、文档和同目录可编辑 `config.toml`，不包含 GROMACS。每个 wheel、
executable 和 archive 不得超过 256 MB。

## Wheel

使用 Python 3.12 或更高版本及锁定的 `uv` 版本构建和审计：

```bash
uv sync --frozen --group dev
uv build
uv run python packaging/verify_wheel.py dist/mdhelper-0.1.0-py3-none-any.whl
```

构建会先创建 sdist，再从该干净源码归档构建 wheel，避免陈旧本地构建目录混入 wheel。审计比较
package 与源码中的模块和资源，并检查大小。在干净环境中测试 wheel：

```bash
uv venv --python 3.12 /tmp/mdhelper-wheel-test
uv pip install --python /tmp/mdhelper-wheel-test/bin/python \
  ./dist/mdhelper-0.1.0-py3-none-any.whl
/tmp/mdhelper-wheel-test/bin/mdhelper --version
/tmp/mdhelper-wheel-test/bin/mdhelper cli --help
```

Linux GUI 安装增加 extra：

```bash
uv pip install --python /tmp/mdhelper-wheel-test/bin/python \
  "./dist/mdhelper-0.1.0-py3-none-any.whl[gui]"
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
dist/linux/MDHelper-0.1.0-Linux-x86_64.tar.gz
dist/linux/MDHelper-0.1.0-Linux-x86_64-GUI.tar.gz
```

构建审计内容和大小，解压每个 archive，并检查版本、TUI 启动、headless fallback、配置、资源
及适用时的 offscreen GUI 启动。

## Windows

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".venv-windows"
uv sync --frozen --group dev
.\packaging\windows\build.ps1 -Python ".venv-windows\Scripts\python.exe"
```

产物为 `dist/windows/MDHelper-0.1.0-Windows-x64.zip`。构建解压 ZIP，并检查全部界面模式、
同目录配置和 package 资源。`config.toml` 必须与 `mdhelper.exe` 同目录。`--settings` 和
`MDHELPER_CONFIG` 可覆盖该路径。

只有目标平台工作流成功后才满足发布门槛。

## 自动化流程

`Quality` 工作流在 pull request、推送到 `main` 和手动触发时运行。Linux 和 Windows job
均会安装锁定环境、校验版本元数据、运行 Ruff、mypy 和完整测试集，然后检查平台对应的启动
路径。Linux job 还会构建和审计 wheel，并将它安装到干净环境中验证。

对默认分支配置以下合并前必须通过的检查：

- `Quality / Linux`
- `Quality / Windows`

Linux 和 Windows 发布候选工作流仍可手动触发，同时暴露可复用工作流入口，供标签发布调用
同一套目标平台构建。每个候选构建都会在上传产物前完成源码校验和打包应用 smoke test。
Dependabot 每周将依赖和工作流 action 更新各自分组为 pull request，更新仍需通过常规质量门禁。

## 发布正式版本

保持 `pyproject.toml` 与 `src/mdhelper/version.py` 的版本一致。修改依赖或项目元数据后，需更新
`uv.lock` 并与改动一起提交。创建标签前运行：

```bash
uv sync --frozen --group dev
uv run python packaging/check_release.py
uv run ruff check conftest.py packaging src tests
uv run mypy src packaging/check_release.py
uv run pytest -q
```

确认 `main` 上的必需检查全部通过后，创建并推送与元数据完全一致的版本标签：

```bash
git tag -a v0.1.0 -m "MDHelper 0.1.0"
git push origin v0.1.0
```

`Release` 工作流会拒绝不匹配的标签，构建 wheel 和三个便携式归档，并等待两个目标平台 job
完成。只有最后的 job 获得 `contents: write` 权限；它下载已验证的产物、生成 `SHA256SUMS`，
并创建带自动生成说明的 GitHub Release。在对应 commit 通过必需检查前，不要创建或移动发布标签。
