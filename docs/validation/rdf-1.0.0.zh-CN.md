# Radial distribution function 验证 - method 1.0.0

[English](rdf-1.0.0.md) | [简体中文](rdf-1.0.0.zh-CN.md)

## 参考体系

自动测试在临时目录构造两帧、四原子的周期 GRO 体系。坐标、盒、选择、帧范围和 histogram
edge 都在测试中显式给出，不依赖外部轨迹或保存的参考曲线。

## 检查内容

测试从期望 shell count 和精确 shell volume 独立构造结果，并用 `pytest.approx` 比较 radius
sample 与归一化 `g(r)`。另一个用例使用重叠的 reference/selection 集合，检查 ordered-pair
normalization 和 self exclusion。Application、CLI、project persistence、export 和 GUI 路径
也使用运行时生成的 GRO 输入。

GROMACS adapter 在受控命令输出边界验证帧范围转换和输入保持。这些检查验证 MDHelper 的
adapter 行为，不声称已经完成独立生产轨迹对照。

## 限制

自包含数值体系刻意保持小型且为正交盒，不证明科学收敛、不确定度、force field 有效性或
不同 GROMACS 版本间的一致性。这些仍需用户针对具体科学数据验证。
