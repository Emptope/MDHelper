# 物种角色

[English](SPECIES.md) | [简体中文](SPECIES.zh-CN.md)

`mdhelper inspect` 按 topology residue identity 划分 species，按 topology 产生的 `molecule_id`
划分 molecule。程序递归扫描 project 目录中的 `.itp` 文件，将 topology residue name 与
`[ moleculetype ]` name 匹配。直接加载文件时，trajectory 所在目录作为自动创建 project 的位置，
也用于查找 `.itp`。

程序使用 decimal arithmetic 累加匹配的 `[ atoms ]` section 中 charge 列。Molecular net charge
大于 `+1e-6 e` 时建议 `cation`，小于 `-1e-6 e` 时建议 `anion`，舍入误差范围内则建议
`solvent`。只含参数的 `.itp` 会被忽略；定义缺失时不产生建议，损坏、重复或依赖 preprocessor
的 molecule 定义会直接报错，不会猜测结果。

所有检测到的 species 都有匹配定义时，检查流程将每种 molecular charge 乘以 molecule 数量后
加和。体系总电荷的绝对值超过 `1e-6 e` 时，GUI 会弹出警告；任一定义缺失时不执行不完整判断。

检查结果包含源文件、molecule atom count、molecular charge 和 zero tolerance。
没有匹配的 molecule definition 时，检查结果改为显示查找失败原因。
自动识别只作为参考：CLI 接受 `--roles '{LI: cation, SOL: solvent}'`，TUI 和 GUI 允许逐项检查
和修改建议。建议仅存在于当前检查 session，不写入 schema；只有用户确认的角色会存入
`request.species_roles` 和 project manifest。`mdhelper project set-roles` 替换项目映射。可用角色
为 `cation`、`anion` 和 `solvent`。

角色只提供 metadata，不创建选择、不决定参数或算法，也不修改结果。
