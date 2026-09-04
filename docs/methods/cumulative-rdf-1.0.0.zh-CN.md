# Cumulative Number RDF - method 1.0.0

[English](cumulative-rdf-1.0.0.md) | [简体中文](cumulative-rdf-1.0.0.zh-CN.md)

Analysis type 为 `cumulative_rdf`，CLI 命令为 `cumulative-rdf`。

## 定义

固定 reference 集合 A、selection 集合 B、第 `f` 帧和请求宽度 `d` 时，`H_fk` 统计
`[k*d,(k+1)*d)` 中的有序非 self A-B pair。Radius `(k+1)*d` 处的值为：

```text
cumulative_number[k] = sum_f sum_{j <= k} H_fj / (number_of_frames * |A|)
```

在对应 bulk RDF normalization 下：

```text
cumulative_number(r) =
    4 * pi * rho_selection * integral_0^r g_reference,selection(r') * r'^2 dr'
```

该值表示每个 reference 原子在 `r` 内的平均 selected-atom 数，不把 atom contact 转为 molecule
count。Result 包含 `radius_nm,cumulative_number`，不包含固定 cutoff 时间序列、逐 reference
count、分组 count 或概率分布。

## 选择、帧、PBC 与网格

选择、帧切片、预处理、box 校验和最小镜像规则与
[RDF method 1.0.0](rdf-1.0.0.zh-CN.md)一致。距离使用 nm，cumulative number 的单位为 count。

`Q = round(2*r_max_nm/bin_width_nm)` 个半宽细 bin 产生 `floor(Q/2)` 个 sample，radius 为
`d,2d,...`。未匹配的末尾细 bin 被忽略。请求宽度不调整为结束于 `r_max_nm`。非法参数、超过
一百万 RDF sample、非法 box、空选择和全 self pair 集合直接失败。

## GROMACS Backend

`analysis_backend = gromacs` 时，存储 sample 来自 `gmx rdf -cn`；同一次运行生成壳层诊断所需
RDF。MDHelper 把 XVG 映射为 `radius_nm,cumulative_number`，不执行积分或重算。该分支的 pair
selection、PBC、grid 和 endpoint 由 GROMACS 决定。帧处理和 provenance 与 RDF method 1.0.0
一致。

术语遵循 [`gmx rdf`](https://manual.gromacs.org/current/onlinehelp/gmx-rdf.html)：UI 使用
**Cumulative Number RDF**，绘图 quantity 为 **Cumulative RDF**，Y-axis label 为 **number**。

## 第一壳层配位数

累计曲线终点不是壳层配位数。MDHelper 从相同的进程内 histogram 生成 RDF，或使用 GROMACS
RDF 输出，查找第一峰和随后最小值，再将不小于该 radius 的第一个累计 sample 报告为
`coordination_number`。

无法识别最小值时 coordination 不可用，累计曲线仍有效。该诊断需要用户确认且不修改曲线。
该规则采用电解液分析中的第一最小值约定，参见 DOI `10.3390/molecules30020230` 和
`10.1038/s41598-024-60063-0`。

## 输出与统计

单结果图把 radius 转为埃，Y label 为 `number`。CSV 文件为 `rdf_cn.csv`，列为
`radius_nm,cumulative_number`。JSON 和 CSV 最多使用 15 位有效数字。

基础结果不含 block size、standard error 或 uncertainty band。本方法不估计平衡、自相关、
收敛、不确定度或有效样本量。

[验证报告](../validation/cumulative-rdf-1.0.0.zh-CN.md)定义自动检查范围和限制。
