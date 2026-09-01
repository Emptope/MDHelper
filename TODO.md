# MDHelper TODO

## IMPORTANT!

- 阅读并遵守 `AGENTS.md` 。
- 阅读并遵守 `docs/ARCHITECTURE.md` 的依赖：GUI/TUI/CLI -> App -> Analysis/Services -> Core。

## 紧急任务（重要性由高到低）

## 待实现功能（重要性由高到低）

## 已完成

- [x] [BugFix] 非默认 GROMACS RDF/CN 帧范围在 App、GUI、TUI 前置校验 `rdf`、`trjconv`、`check` capabilities。
- [x] [Feature] Energy 组合图使用 `energy-<term1>-<term2>-...` 命名。
- [x] [BugFix] Open Plot Window 与 Save Plot、Export 保持绘图内容比例一致。
- [x] [Feature] 统一 GUI/TUI 的 RDF/CN 图片导出：结果导出保存单项图，组合 Save Plot 使用 `rdf-cn` 递增命名。
- [x] [BugFix] Stop frame 越界提示显示实际 `Total frame count`。
- [x] [Feature] 修改 TUI 导出分析绘图和分析结果行为，使其与 GUI 行为一致。
- [x] [BugFix] 修复 Stop frame 设置大于总帧数时没有报错的问题。

## 完成标准（每轮改动后需重新确认）

- Linux 全部测试通过；Windows `.venv-windows` 全部测试通过。
- 架构测试能阻止跨层导入、TUI/GUI/CLI 混放和根目录兼容壳回归。
- GUI 文件驱动的自动刷新回归测试通过，更新输入不保留过期检测结果。
- Ruff 和 mypy 通过，包括已安装 Qt 类型信息的 GUI 检查。
