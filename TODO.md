# MDHelper TODO

## IMPORTANT!

- 阅读并遵守 `AGENTS.md` 。
- 阅读并遵守 `docs/ARCHITECTURE.md` 的依赖：GUI/TUI/CLI -> App -> Analysis/Services -> Core。

## 紧急任务（重要性由高到低）


## 待实现功能（重要性由高到低）

## 已完成

- [x] [Maintenance] GUI Analysis 页 Progress 区域的按钮按 `Run`、`Cancel` 的顺序排列。
- [x] [Maintenance] GUI Analysis 页将 `Analysis type` 改为 `Type`，`Analysis backend` 改为 `Backend`，`Analysis Progress` 改为 `Progress`。
- [x] [Fix] Job Log 补充最小化、最大化和关闭窗口控制；默认跟随并显示最新日志，用户向上滚动时保留位置；连续重复的进度 message 只记录一次；`Copy` 成功后用非模态弹窗提示用户；将 `Details` 按钮移到进度条右边。
- [x] [Feature] GUI `Analysis Settings` 标题改成 `Analysis`；`Analysis progress` 改成 `Analysis Progress`； 把 `Run` 和 `Cancel` 按钮与 `Analysis Progress` 对齐，进度条移动到下方；在最下方 status bar 的右边增加一个 `Details` 按钮，打开呈现 Log Page，上方标题是 <TASK_NAME> 或者 <WORKFLOW_NAME> （Workflow 功能暂未实现）；中间信息框展示 raw log messages；Log Page 右下方设置有 `Copy` 按钮，点击可以复制 log；Log Page 应该是悬浮窗口，不影响主菜单交互。
- [x] [Maintenance] 将现有任务执行架构和相关命名改为 `jobs`，保留 `workflow` 给未来的用户编排任务功能，暂不实现 Workflow 功能。
- [x] [Maintenacne] 按设计要求重构 GUI 文件夹，不改动 GUI 现有布局和功能，只整理代码架构和清理无用代码。

## 完成标准（每轮改动后需重新确认）

- Linux 全部测试通过；Windows `.venv-windows` 全部测试通过。
- Ruff 和 mypy 通过。
