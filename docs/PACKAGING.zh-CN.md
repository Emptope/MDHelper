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
uv build --wheel
uv run python packaging/verify_wheel.py dist/mdhelper-0.1.0-py3-none-any.whl
```

审计比较 package 与源码中的模块和资源，并检查大小。在干净环境中测试 wheel：

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

只有目标平台工作流成功后才满足发布门槛；文件存在不表示测试通过。
