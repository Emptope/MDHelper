# RDF 验证 - method 1.0.0

[English](rdf-1.0.0.md) | [简体中文](rdf-1.0.0.zh-CN.md)

测试生成两帧、四原子的周期 GRO 体系，独立计算 shell count 和 volume，并比较每个 radius 与
`g(r)` sample。重叠选择检查有序归一化和 self exclusion。生成输入还覆盖 Application、CLI、
GUI、project 和 export 路径。

受控 GROMACS 输出检查命令参数、帧转换、输入保持和 XVG 映射，不提供独立的生产轨迹对照。

该 fixture 检查计数和归一化，不证明收敛、不确定度、force field 有效性、生产规模性能或
不同 GROMACS 版本的一致性。
