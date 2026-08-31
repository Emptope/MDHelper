# Cumulative RDF 验证 - method 1.0.0

[English](cumulative-rdf-1.0.0.md) | [简体中文](cumulative-rdf-1.0.0.zh-CN.md)

## 参考体系

自动测试使用与 RDF 验证相同的运行时生成两帧周期 GRO 体系，不依赖外部 MD 目录或保存的
XVG 曲线。

## 检查内容

测试显式给出每个 bin 的期望 pair count，再用 NumPy 独立累加。每个 radius sample 和
cumulative number 都与分析结果比较。测试还使用生成输入覆盖 backend neutrality、帧切片、
project persistence、CSV/JSON export、绘图、CLI 和 GUI 路径。

GROMACS command adapter 使用受控 process output 验证参数构造和序列化曲线处理，不把一次
外部程序运行保存为固定真值。

## 限制

该体系验证确定性计数和积分行为，不验证收敛、统计不确定度、化学解释或生产规模性能。
