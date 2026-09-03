# MDHelper TODO

## IMPORTANT!

- 阅读并遵守 `AGENTS.md` 。
- 阅读并遵守 `docs/ARCHITECTURE.md` 的依赖结构。

## 紧急任务（重要性由高到低）

## 待实现功能（重要性由高到低）

## 已完成

- [x] [Feature] 实现用户编排 workflow 功能：用户在 `config.toml` 中可以按照分析项目名称编排固定 workflow，选择 `Tools` -> `Run Workflow...` 可以选择不同的 workflow，并且进入执行 workflow 前的每个项目审查界面，用户配置好后可以直接执行。`Run Workflow...` 按钮放在 `Open Terminal Interface` 下方。
- [x] [Feature] `Help` 按钮下拉菜单加入 `Documents`，悬浮或点击可以选择各种软件的官网链接，比如 [MDAnalysis](https://www.mdanalysis.org/), [GROMACS](https://manual.gromacs.org/documentation/current/index.html)，[LAMMPS](https://docs.lammps.org/Manual.html)，[CP2K](https://manual.cp2k.org/trunk/)，[VASP](https://vasp.at/wiki/The_VASP_Manual)，[VMD](https://www.ks.uiuc.edu/Research/vmd/current/ug/)。

## 完成标准（每轮代码改动后需重新确认）

- Ruff 和 mypy 通过。
- Windows/Linux 全部测试通过。
