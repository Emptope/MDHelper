# MDHelper TODO

## IMPORTANT!

- 阅读并遵守 `AGENTS.md` 。
- 阅读并遵守 `docs/ARCHITECTURE.md` 的依赖：GUI/TUI/CLI -> App -> Analysis/Services -> Core。

## 紧急任务（重要性由高到低）

- [ ] [Fix] 修改 TUI "Input files and inspection" 标题，目前这个标题太含糊；这个模块下的 2 和 3 子功能重叠了，保留 "Show current system summary"。
- [ ] [Fix] 清理 TUI 中的 "="，统一替换成 "\*\*\*标题\*\*\*"，运行分析时，不要出现装饰。

## 待实现功能（重要性由高到低）

## 已完成

- [x] [Test] Remove redundant waits and setup from the test suite.

## 完成标准（每轮改动后需重新确认）

- Linux 全部测试通过；Windows `.venv-windows` 全部测试通过。
- Ruff 和 mypy 通过。
