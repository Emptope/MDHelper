# Cumulative RDF 验证 - method 1.0.0

[English](cumulative-rdf-1.0.0.md) | [简体中文](cumulative-rdf-1.0.0.zh-CN.md)

测试使用 RDF 验证生成的两帧周期 GRO 体系，独立累计期望 bin count，并比较每个 radius 和 cumulative-number sample。生成输入还覆盖帧切片、Application、CLI、GUI、project、plot 和 export 路径。

受控 GROMACS 输出检查命令参数和 XVG 映射。回归测试验证配位数取自原始 RDF 首谷对应的累计样本，不额外舍入；两个原始 XVG 文件在临时目录清理、项目重载和导出后均保持完整。不作为保存的参考数据。

该 fixture 检查计数和累加，不证明收敛、不确定度、化学解释或生产规模性能。
