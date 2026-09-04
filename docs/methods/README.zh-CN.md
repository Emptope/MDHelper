# 带版本的方法

[English](README.md) | [简体中文](README.zh-CN.md)

Result 通过 request 中的 `analysis_type` 和 result 中的 `method_version` 标识方法。数值定义变化
需要新 method version；展示和保持数值等价的性能修改不需要。

| 分析 | 方法 | 验证 |
| --- | --- | --- |
| RDF | [1.0.0](rdf-1.0.0.zh-CN.md) | [报告](../validation/rdf-1.0.0.zh-CN.md) |
| Cumulative Number RDF | [1.0.0](cumulative-rdf-1.0.0.zh-CN.md) | [报告](../validation/cumulative-rdf-1.0.0.zh-CN.md) |

方法存储 nm 和 ps，使用固定 atom identity，并报告所选帧上的确定值。方法不包含不确定度估计。
