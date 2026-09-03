# Cumulative RDF 验证 - method 1.0.0

[English](cumulative-rdf-1.0.0.md) | [简体中文](cumulative-rdf-1.0.0.zh-CN.md)

测试使用 RDF 验证生成的两帧周期 GRO 体系，独立累计期望 bin count，并比较每个 radius 和
cumulative-number sample。生成输入还覆盖帧切片、Application、CLI、GUI、project、plot 和
export 路径。

受控 GROMACS 输出检查命令参数和 XVG 映射，不作为保存的参考数据。

该 fixture 检查计数和累加，不证明收敛、不确定度、化学解释或生产规模性能。
