# MDHelper TODO

## IMPORTANT!

- 阅读并遵守 `AGENTS.md` 。
- 阅读并遵守 `docs/ARCHITECTURE.md` 的依赖：GUI/TUI/CLI -> App -> Analysis/Services -> Core。

## 紧急任务（重要性由高到低）

## 待实现功能（重要性由高到低）

## 已完成

- [x] [Fix] GUI Result 页 `Advanced` 按钮改成 `Advanced...`
- [x] [Feature] 增设一个功能：Tools 最下方增设 `Make Index File...` 选项，实现逻辑：当用户未配置 GROMACS 时，打开信息页，告诉用户如何用 `gmx make_ndx` 制作 index file，并附上 https://manual.gromacs.org/documentation/current/onlinehelp/gmx-make_ndx.html ；当用户配置 GROMACS 时，打开外部终端，调用 GROMACS 执行 `<gmx_executable> make_ndx -f <.gro> -o index.ndx` 命令。

## 完成标准（每轮代码改动后需重新确认）

- Linux 全部测试通过；Windows `.venv-windows` 全部测试通过。
- Ruff 和 mypy 通过。
