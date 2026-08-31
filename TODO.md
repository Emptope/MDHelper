# MDHelper TODO

## IMPORTANT!

- 阅读并遵守 `AGENTS.md` 。
- 阅读并遵守 `docs/ARCHITECTURE.md` 的依赖：GUI/TUI/CLI -> App -> Analysis/Services -> Core。

## 紧急任务（重要性由高到低）

## 待实现功能（重要性由高到低）

## 已完成

- [x] [Performance] GUI 启动速度太慢，优化启动速度

## 完成标准（每轮改动后需重新确认）

- Linux 全部测试通过；Windows `.venv-windows` 全部测试通过。
- 架构测试能阻止跨层导入、TUI/GUI/CLI 混放和根目录兼容壳回归。
- GUI 文件驱动的自动刷新回归测试通过，更新输入不保留过期检测结果。
- Ruff 和 mypy 通过，包括已安装 Qt 类型信息的 GUI 检查。
