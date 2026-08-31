# 带版本的方法

[English](README.md) | [简体中文](README.zh-CN.md)

这些文档规范 MDHelper 0.1.0 的分析结果。结果通过 `analysis_type` 和 `method_version` 标识
方法；任何可能改变数值定义的修改都必须产生新 method version。只改变展示或保持规范数值
不变的性能优化不需要新方法版本。

| 分析 | 方法规范 | 验证报告 |
| --- | --- | --- |
| RDF | [rdf-1.0.0.zh-CN.md](rdf-1.0.0.zh-CN.md) | [rdf-1.0.0.zh-CN.md](../validation/rdf-1.0.0.zh-CN.md) |
| 累积 RDF（UI：Cumulative Coordination Number） | [cumulative-rdf-1.0.0.zh-CN.md](cumulative-rdf-1.0.0.zh-CN.md) | [cumulative-rdf-1.0.0.zh-CN.md](../validation/cumulative-rdf-1.0.0.zh-CN.md) |

所有方法存储 nm 和 ps。进程内轨迹方法使用固定 atom identity、流式帧和共享的
[选择契约](../SELECTIONS.zh-CN.md)。显式 GROMACS RDF/CN 遵循对应方法章节记录的
`gmx rdf` selection 与 sampling 规则；所选 Backend 是结果定义和 provenance 的一部分。

基础结果是记录的轨迹、选择、帧范围和参数的确定函数，不包含固定 block size 或 standard
error。未来统计分析必须显式启用并独立于基础方法。
