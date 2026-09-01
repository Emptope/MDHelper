# MDHelper TODO

## IMPORTANT!

- 阅读并遵守 `AGENTS.md` 。
- 阅读并遵守 `docs/ARCHITECTURE.md` 的依赖：GUI/TUI/CLI -> App -> Analysis/Services -> Core。

## 紧急任务（重要性由高到低）

## 待实现功能（重要性由高到低）

## 已完成

- [x] [BugFix] GUI 打开新项目目录时立即创建 figures 和 results，并在结果完成后启用 Save Plot。
- [x] [Feature] GUI Save Plot 使用分析目录命名规则平铺保存图片；Export 将独立图片保存到对应分析目录。
- [x] [BugFix] 解决多个窗口 Plot 时选择 Save Plot 保存到同一张图片的问题，需要保存到不同图片中。
- [x] [BugFix] 解决 GROMACS 后端当 stride > 1 时合成帧结束后卡死的问题。

## 完成标准（每轮改动后需重新确认）

- Linux 全部测试通过；Windows `.venv-windows` 全部测试通过。
- 架构测试能阻止跨层导入、TUI/GUI/CLI 混放和根目录兼容壳回归。
- GUI 文件驱动的自动刷新回归测试通过，更新输入不保留过期检测结果。
- Ruff 和 mypy 通过，包括已安装 Qt 类型信息的 GUI 检查。
