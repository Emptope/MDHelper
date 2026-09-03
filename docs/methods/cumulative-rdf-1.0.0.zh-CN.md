# Cumulative Number RDF - method 1.0.0

[English](cumulative-rdf-1.0.0.md) | [简体中文](cumulative-rdf-1.0.0.zh-CN.md)

状态：MDHelper 0.1.0 发布方法规范。

序列化 analysis type 为 `cumulative_rdf`，MDHelper CLI 命令为 `cumulative-rdf`。GROMACS
2026.3 文档说明 `gmx rdf -cn` 生成 **cumulative number RDF**，输出文件说明为
**Cumulative RDFs**，默认 basename 为 `rdf_cn`。GROMACS 实现将图标题设为
**Cumulative Number RDF**，Y 轴设为 **number**；MDHelper 使用相同的用户可见表述。

## 量与适用范围

对进程内后端，固定 reference 集合 A、selection 集合 B、第 `f` 帧和请求宽度 `d`，令
`H_fk` 为 `[k*d,(k+1)*d)` 内有序非 self A-B pair 数。这些 bin 由 RDF 共用的半宽细
histogram 两两合并得到。在 radius `(k+1)*d` 输出的累计曲线为：

```text
cumulative_number[k] = sum_f sum_{j <= k} H_fj / (number_of_frames * |A|)
```

在本方法 bulk RDF 归一化下，同一量数学上为：

```text
cumulative_number(r) =
    4 * pi * rho_selection * integral_0^r g_reference,selection(r') * r'^2 dr'
```

该累计数表示每个 reference 原子周围半径 `r` 内平均有多少个 selection 原子。与 reference
拓扑索引相同的 selection 原子作为 self pair 排除。结果 data 只含 `radius_nm` 和
`cumulative_number`，不生成固定 cutoff 时间序列、逐 reference count、residue 分组 count
或 count 概率分布。

selection 决定计数基准并始终显示在报告中。例如 `Li-O_FSI` 表示每个所选 Li 的 O_FSI atom
contact 数。每个 FSI 只选一个代表原子时，该值才等同于不同 FSI 阴离子数。MDHelper 不会
静默把 atom contact 改成 molecule count。

累积分析必须显式运行或加载。RDF 结果只含 `g(r)`，不会隐式附带 cumulative RDF 曲线。

## GROMACS 后端

`analysis_backend = gromacs` 时，存储的累计 sample 直接来自同一次 `gmx rdf` 的 `-cn` 输出；该次
运行也生成用于第一壳层诊断的 RDF。MDHelper 把 XVG 标准化为
`radius_nm,cumulative_number`，不积分 `g(r)`，也不重算 pair count。该分支的累计定义、
grid、PBC 和 endpoint 由 GROMACS 决定；精确 Python 帧切片、selection syntax 和
Integration provenance 遵循 RDF method 1.0.0。

## 选择、帧、单位、PBC 与网格

进程内静态选择、帧范围、box 校验、预处理记录和三斜盒最小镜像与 RDF method 1.0.0
相同；GROMACS 分支遵循对应 GROMACS RDF 规则。距离为 nm，累计数单位为 count。

request 记录 `reference`、`selection`、`r_max_nm` 和 `bin_width_nm`。进程内后端建立
`Q = round(2*r_max_nm/bin_width_nm)` 个半宽细 bin。cumulative RDF 在 `d,2d,...` 输出
`floor(Q/2)` 个 sample；无法配对的末尾细 bin 会像 `gmx rdf -cn` 一样忽略。请求宽度保持
不变，不调整为恰好结束于 `r_max_nm`。每个所选帧都校验 `r_max_nm` 不超过可靠最小镜像
半径。空选择、全 self pair、非法 box/径向参数或超过一百万 RDF sample 会产生可行动错误。

## 第一壳层 coordination number

该 cumulative RDF 是非递减累计曲线；全局最小值通常位于零距离端，全局最大值通常位于
`r_max_nm`。全局极值与终点值缺少自动化学意义，因此 MDHelper 不用这些值总结壳层
coordination number。

第一壳层报告遵循常用电解液模拟约定：

1. 用相同 pair histogram 和归一化生成 RDF；
2. 按 RDF method 1.0.0 找第一显著峰和随后的第一最小值；
3. 以该最小值半径作为壳层边界；
4. 在第一个不小于该 RDF radius 的 cumulative-RDF endpoint 报告 `cumulative_number` 为单值
   `coordination_number`，并附边界与置信度。

完整曲线仍叫 cumulative number。没有可靠最小值时，第一壳层值 unavailable，但完整曲线
保留；不会使用终点值、任意斜率或写死 cutoff。该诊断需要用户复核且不改变曲线。

Pierini 等使用积分到第一最小值的 RDF running number 得到第一 Li 壳层配位数
（Molecules 2025，DOI `10.3390/molecules30020230`）。Mabrouk 等用第一 RDF 峰面积和对应第一
最小值报告 Li 配位（Scientific Reports 2024，DOI `10.1038/s41598-024-60063-0`）。

## 确定性与统计范围

固定轨迹、选择、帧范围和数值参数时，本方法报告所有所选帧的确定累计曲线。基础 request
没有 block-size 参数，结果没有 standard error 或 uncertainty band。本方法不估计平衡、
自相关、收敛、不确定度或有效样本量；未来统计分析必须独立、显式启用，从可审计时间序列
开始并保持基础曲线不变。

## 绘图与导出

单结果图 X 轴以埃显示距离，Y 轴标签为 **number**。存储数据仍为 nm。显式选择 RDF 和
累积结果时，可共享距离 X 轴，`g(r)` 在主 Y 轴，**Cumulative RDF** series 在次 Y 轴，
两套 Y scale 独立，自动 X 范围取可见 domain 交集。

CSV 为 `rdf_cn.csv`，列是 `radius_nm,cumulative_number`，不包含 uncertainty、probability 或
distribution。JSON/CSV 最多写 15 位有效数字，不改变内存计算。

## GROMACS 术语来源

- [GROMACS 2026.3 `gmx rdf` 手册](https://manual.gromacs.org/current/onlinehelp/gmx-rdf.html)
- [GROMACS `rdf.cpp` 实现](https://gitlab.com/gromacs/gromacs/-/blob/main/src/gromacs/trajectoryanalysis/modules/rdf.cpp)

## 验证契约

自动验证使用运行时生成、可手算的周期体系，将每个 radius sample 和 cumulative value 与
独立累加的 histogram 比较。GROMACS adapter 另在受控命令边界验证。详见匹配版本验证报告。
