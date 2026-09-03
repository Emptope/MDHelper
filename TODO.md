# MDHelper TODO

## IMPORTANT!

- 阅读并遵守 `AGENTS.md` 。
- 阅读并遵守 `docs/ARCHITECTURE.md` 的依赖结构。

## 紧急任务（重要性由高到低）

## 待实现功能（重要性由高到低）

## 已完成

- [x] [Feature] Role 只保留 `cation` `anion` `solvent` 三种角色，程序实现：自动读取 Project 文件夹下的 `.itp` 文件，根据其中的 [ moleculetype ] 字段记载的残基名称与其中 [ atoms ] 字段记载的电荷加和，自动判断其是这三种角色中的哪个，`cation`: charge > 0, `anion`: charge < 0, `solvent`: charge = 0。

## 完成标准（每轮代码改动后需重新确认）

- Ruff 和 mypy 通过。
- Windows/Linux 全部测试通过。
