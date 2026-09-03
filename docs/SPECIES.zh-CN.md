# 物种角色

[English](SPECIES.md) | [简体中文](SPECIES.zh-CN.md)

`mdhelper inspect` 按 topology residue identity 划分 species，按 topology 产生的 `molecule_id`
划分 molecule。Residue name 不决定化学角色。

Charge 完整时，molecular net charge 大于 `+0.25 e` 建议 `cation`，小于 `-0.25 e` 建议
`anion`。唯一且数量最多的中性 species 得到 low confidence `solvent` 建议。Charge 缺失、
符号混合或中性数量并列时不产生建议。

检查结果包含 method、evidence、confidence、candidate、reason 和 confirmation 状态。CLI 接受
`--roles '{LI: cation, SOL: solvent}'`；TUI 和 GUI 提供相同选择。确认的角色存入
`request.species_roles` 和 project manifest。`mdhelper project set-roles` 替换项目映射。可用角色
为 `cation`、`anion`、`solvent`、`additive`、`polymer`、`surface` 和 `other`。

角色只提供 metadata，不创建选择、不决定参数或算法，也不修改结果。
