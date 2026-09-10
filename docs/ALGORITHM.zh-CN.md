# MDHelper 算法实现说明

[English](ALGORITHM.md) | [简体中文](ALGORITHM.zh-CN.md)

科学定义、归一化、端点和限制以版本化的 [RDF](methods/rdf-1.0.0.zh-CN.md) 与[累计 RDF](methods/cumulative-rdf-1.0.0.zh-CN.md) 方法为准。本文只补充实现决策。

## Backend 分派

`auto` 按注册顺序尝试完整 backend：先 MDAnalysis，再 GROMACS。加载失败可进入下一次尝试，显式选择则不回退。Provenance 同时记录请求值和实际 backend；一次尝试的加载、选择、帧处理与计算由同一个 backend 负责。

MDAnalysis 保留原子顺序，将坐标和盒子从 angstrom 一次转换为 nm，核心帧采用 NumPy `float64`。分子 ID 为 `segid:residue_name:residue_id`；缺失的有限电荷保留为 null，缺失元素只按原子名回退，不进行化学推断。选择语法、NDX 校验与建议物种角色见[选择说明](SELECTIONS.zh-CN.md)。

## 周期几何与网格

盒矩阵 `H` 的每一行是一个晶胞向量：

```text
V = abs(det(H))
h_i = 1 / norm(inverse(H)[:, i])
r_limit = min(h_i) / 2
```

每一帧要求有限的 `V > 1e-12 nm^3`，且 `r_max <= r_limit + max(1e-12, r_limit * 1e-10)`。MDAnalysis `capped_distance` 使用完整盒参数计算最小镜像距离，排除相同拓扑索引的原子对，保留位于 cutoff 的距离。

细网格为 `Q = max(1, round(2*r_max/bin_width))` 个半宽 bin，重采样遵循版本化方法。半径舍入至小数点后 15 位，RDF 最多一百万个样本。`FrameAudit` 记录实际帧索引、时间和数量。

GROMACS 提供自身曲线。非默认帧范围要求 `check` 和 `trjconv -fr`，而不是 `rdf -dt`。XVG 必须包含有限、递增的半径及两列数据；MDHelper 不重算 GROMACS 的归一化或累计积分。

## 第一配位壳诊断

诊断只处理已完成 RDF 的副本，不修改原曲线。至少需要 11 点，使用最大 11 点的 Savitzky-Golay 窗口，然后寻找第一个合格峰及其后的极小值：

```text
peak prominence floor = max(0.05, 0.05 * max(smoothed_rdf))
minimum prominence floor = max(0.02, peak_floor / 2)
```

缺少任一特征时边界不可用，并产生警告。可用边界必须经用户确认，且不改变 `r_max`。累计配位数按累计方法定义，取边界处或其后的首个样本。

## 绘图与 Provenance

径向绘图将 nm 转换为 angstrom，能量时间轴使用 ps。兼容径向序列采用 X 范围交集，RDF 使用主轴，累计 RDF 使用副轴。自动 Y 范围从零开始，只考虑可见范围内有限值；用户设置优先。物种颜色按排序后的名称分配，固定颜色采用存储 ID，副轴曲线更暗且使用虚线。标题必须可打印、单行且最多 120 字符。绘图不修改结果数组。

进程内输入以 4 MiB 分块计算 SHA-256。直接 GROMACS 调用记录路径和命令，不预先遍历哈希。Provenance 包含版本、平台、字节序、输入、backend 分派、配置来源、角色及参数决策。持久化、Job 取消与进程边界见[架构](ARCHITECTURE.zh-CN.md)。

径向计算最坏时间为 `O(F * N_R * N_S)`，额外内存为 `O(N_R + N_S + P + B)`，分别涉及帧数、参考与选择原子数、返回原子对和 bin 数。单次距离搜索可能延迟取消。算法修改应同步受影响的方法版本、验证、schema 和回归测试，不得添加针对特定样本或输出的例外。
