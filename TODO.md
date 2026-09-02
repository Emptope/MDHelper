# MDHelper TODO

## IMPORTANT!

- 阅读并遵守 `AGENTS.md` 。
- 阅读并遵守 `docs/ARCHITECTURE.md` 的依赖：GUI/TUI/CLI -> App -> Analysis/Services -> Core。

## 紧急任务（重要性由高到低）

## 待实现功能（重要性由高到低）

## 已完成

- [x] [Maintenance] 清理 tests 代码，降低测试耗时，删除冗余的 "assert xx in xx" "assert xx not in xx" 测试，目前是快速开发阶段，UI 变动频繁，不应有这种测试。
- [x] [Fix] 解决 Theme 切换后字号不统一的问题。

## 完成标准（每轮改动后需重新确认）

- Linux 全部测试通过；Windows `.venv-windows` 全部测试通过。
- Ruff 和 mypy 通过。
