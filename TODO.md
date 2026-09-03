# MDHelper TODO

## IMPORTANT!

- 阅读并遵守 `AGENTS.md` 。
- 阅读并遵守 `docs/ARCHITECTURE.md` 的依赖：GUI/TUI/CLI -> App -> Analysis/Services -> Core。

## 紧急任务（重要性由高到低）

## 待实现功能（重要性由高到低）

## 已完成

- [x] [Feature] GUI Load 页 Detect Species and Roles 下方按钮布局重新设计，`Help` 按钮移动到左边，删掉 `Review Suggestions`，右边放置 `Detail Suggestions` `Apply` 和 `Cancel` 按钮，用户 `Apply` 后自动保存 Roles，`Cancel` 后清除所有 Suggest Roles，`Detail Suggestions` 显示具体推荐信息，文本需要 format，`Help` 页面用 `Role` `Meaning` 两列表格形式提供，窗口控件只保留`关闭`。
- [x] [Feature] GUI 所有有链接的 Help 或 Hint 页面的 URL 左边加上 "More info: <URL>"
- [x] [Feature] GUI Result 页 `Result overview` 改成 `Overview`，同时把 `Technical details` 隐藏，下方增设两个按钮，左边为 `Logs`，右边为 `Details`，`Logs` 打开程序运行日志，`Details` 打开详细结果页，顶端 bar 标题为 <JOB_NAME> 或者 <WORKFLOW_NAME>，下方有 `Copy` 按钮。
- [x] [Fix] 隔离测试运行日志与用户日志。
- [x] [Fix] 删除 GUI Result 页的 Logs 按钮和运行日志查看入口，保留 Details。

## 完成标准（每轮代码改动后需重新确认）

- Linux 全部测试通过；Windows `.venv-windows` 全部测试通过。
- Ruff 和 mypy 通过。
