# MDHelper TODO

## IMPORTANT!

- 阅读并遵守 `AGENTS.md` 。
- 阅读并遵守 `docs/ARCHITECTURE.md` 的依赖：GUI/TUI/CLI -> App -> Analysis/Services -> Core。

## 紧急任务（重要性由高到低）

## 待实现功能（重要性由高到低）

## 已完成

- [x] [UI] TUI 主菜单删除冗余 Current inputs 状态。
- [x] [BugFix] TUI 分析运行删除全部 Review setup 和二次确认。
- [x] [BugFix] TUI 径向分析首次选择自动加入任务队列。
- [x] [Feature] 同类多序列合并图使用固定分析名和数字编号。
- [x] [BugFix] TUI RDF/CN 队列按显式分析类型逐项执行，Run task queue 不再二次确认。
- [x] [BugFix] TUI 径向任务队列提供完整的 Add task 编辑流程。
- [x] [Feature] TUI RDF/CN 实现一个类似 GUI 的任务队列，并且目前 RDF+CN 导出的图片中，没有类似 GUI "Save Plot" 的合并绘制图片。
- [x] [Feature] TUI Energy terms 以横纵列表方式列出，不要全部纵向列出。

## 完成标准（每轮改动后需重新确认）

- Linux 全部测试通过；Windows `.venv-windows` 全部测试通过。
- 架构测试能阻止跨层导入、TUI/GUI/CLI 混放和根目录兼容壳回归。
- GUI 文件驱动的自动刷新回归测试通过，更新输入不保留过期检测结果。
- Ruff 和 mypy 通过，包括已安装 Qt 类型信息的 GUI 检查。
