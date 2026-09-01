# MDHelper TODO

## IMPORTANT!

- 阅读并遵守 `AGENTS.md` 。
- 阅读并遵守 `docs/ARCHITECTURE.md` 的依赖：GUI/TUI/CLI -> App -> Analysis/Services -> Core。

## 紧急任务（重要性由高到低）

## 待实现功能（重要性由高到低）

## 已完成

- [x] [BugFix] GROMACS RDF 多余生成 CN，且项目运行的 GROMACS 工作文件未进入项目 cache。
- [x] [BugFix] GROMACS 运行时显示完整命令且 Export 缺少原始输出文件。
- [x] [BugFix] GROMACS 后端分析前执行多余的轨迹预处理与输入指纹，并且运行时不显示原始命令。
- [x] [BugFix] GROMACS 后端分析时进程卡死。
- [x] [BugFix] MDHelper GRO Reader 无法使用，并且错误出现后分析进程未终止。

## 完成标准（每轮改动后需重新确认）

- Linux 全部测试通过；Windows `.venv-windows` 全部测试通过。
- 架构测试能阻止跨层导入、TUI/GUI/CLI 混放和根目录兼容壳回归。
- GUI 文件驱动的自动刷新回归测试通过，更新输入不保留过期检测结果。
- Ruff 和 mypy 通过，包括已安装 Qt 类型信息的 GUI 检查。
