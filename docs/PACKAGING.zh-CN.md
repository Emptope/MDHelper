# 打包与发布验证

[English](PACKAGING.md) | [简体中文](PACKAGING.zh-CN.md)

MDHelper 的发布包按平台分类，每个平台包都是便携归档：

- Linux x86_64 无头版：`tar.gz` 内包含唯一的独立 `mdhelper` 程序、双语文档和同目录可编辑
  `config.toml`；程序内置 TUI、CLI，并明确排除 PySide6。
- Linux x86_64 GUI 版：第二份 `tar.gz` 使用相同的便携目录结构并包含全部三个界面；内置
  GUI 所需的 Qt Widgets runtime 以及 X11、Wayland、offscreen 平台插件。
- Windows x64：包含唯一的 `mdhelper.exe`、双语文档和同目录可编辑 `config.toml`
  的 ZIP；不需要安装或管理员权限，是唯一的 Windows 产物。

Python wheel 是独立的源码环境安装路径，包含统一 `mdhelper` 启动器；除非显式安装
`gui` extra，否则不包含 PySide6。

每个 wheel、独立程序和便携归档都受 256 MB 强制上限约束；任一产物超限即
构建失败。冻结内容审计还会拒绝重复的测试/构建 runtime、未使用的分析模块和平台不需要
的 Qt 组件。

## Linux 构建

在 Linux x86_64 的锁定 GUI 开发环境中执行：

```bash
uv sync --frozen --extra gui --group dev
PYTHON=.venv/bin/python ./packaging/linux/build.sh
```

两份产物分别为 `dist/linux/MDHelper-0.1.0-Linux-x86_64.tar.gz` 和
`dist/linux/MDHelper-0.1.0-Linux-x86_64-GUI.tar.gz`。无头版会拒绝 PySide6，GUI 版只保留
程序所需的 Qt 模块与桌面插件；两者都会拒绝测试/构建工具，分别检查程序和归档的 256 MB
上限，再解压最终归档并实际启动其中的程序。smoke test 会验证版本、显式 TUI、无 display
时的无参数 TUI 降级、便携配置和读取资源的 CLI 命令；GUI 版还会通过 offscreen 平台插件
启动 Qt。解压无头版后运行：

```bash
./mdhelper
./mdhelper tui
./mdhelper cli --help
```

用户不需要安装 Python。在 Linux 桌面解压 GUI 版后，可运行 `./mdhelper` 或
`./mdhelper gui` 打开 GUI；该归档同样保留 TUI 和 CLI。

## Windows 构建

在 Windows x64 的锁定开发环境中执行：

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".venv-windows"
uv sync --frozen --group dev
.\packaging\windows\build.ps1 `
  -Python ".venv-windows\Scripts\python.exe"
```

产物为 `dist/windows/MDHelper-0.1.0-Windows-x64.zip`。构建会解压实际 ZIP，并验证
唯一程序的全部界面模式、同目录配置和内置资源。归档包含 runtime、核心依赖、
method/validation 文档、配置、schema 和依赖/版本/license inventory，不捆绑 GROMACS。

解压后 `config.toml` 和 `mdhelper.exe` 必须放在一起。无参数时优先进入
GUI，GUI 不可用时降级到 TUI；可用 `gui`、`tui`、`cli` 显式选定模式。启动 GUI 时不会
保留控制台窗口：外层控制台启动器创建独立的无控制台 GUI 进程后退出。显式终端模式会保持
连接到启动它的终端，必要时自行创建。所有冻结程序都自动使用同目录 `config.toml`。显式
`--settings` 或
`MDHELPER_CONFIG` 仍优先。
