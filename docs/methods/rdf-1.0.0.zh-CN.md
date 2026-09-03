# 径向分布函数 - method 1.0.0

[English](rdf-1.0.0.md) | [简体中文](rdf-1.0.0.zh-CN.md)

状态：随 MDHelper 0.1.0 发布。

## 定义

固定 reference 集合 A、selection 集合 B、第 `f` 帧和请求 bin width `d` 时，sample `k` 以
`k*d` 为中心。`k = 0` 的 shell 为 `[0,d/2)`，其余为 `[(k-1/2)d,(k+1/2)d)`。`H_fk`
统计该 shell 中排除相同 topology index 后的有序 A-B pair。帧体积为 `V_f`，shell volume 为
`Delta V_k`：

```text
Delta V_0 = (4*pi/3) * (d/2)^3
Delta V_k = (4*pi/3) * [((k+1/2)d)^3 - ((k-1/2)d)^3], k > 0
g_k = sum_f H_fk / (|A| Delta V_k sum_f (|B| / V_f))
```

该式对应默认 `gmx rdf -norm rdf` normalization。Self exclusion 不会把分母中的 `|A||B|`
替换为 `|A||B|-|A intersection B|`。存储和导出的 `g(r)` 不平滑。

本方法适用于三维周期 bulk 轨迹的 atom-based RDF，不支持 slab、非周期、取向、质心、
site-exclusion、仅分子间或动态选择变体。

## 选择、帧与 PBC

MDAnalysis 使用 NDX group 或静态 MDAnalysis expression。GROMACS 使用 NDX group 或原生
expression。帧范围遵循零基 Python slicing：`start` 包含，`stop` 不包含，stride 相对
`start`。

坐标和 radius 使用 nm，`g(r)` 无量纲。每个 pair 使用三斜盒最小镜像。每个处理帧的
`r_max_nm` 不得超过最短垂直 cell height 的一半。缺失、奇异或零体积 box 非法。坐标不做
unwrap、center、fit 或 align。

## 网格

`Q = round(2*r_max_nm/bin_width_nm)` 个半宽细 bin 产生 `floor((Q+1)/2)` 个 RDF sample，
radius 为 `0,d,2d,...`。细 bin 左闭右开，未匹配的末尾细 bin 被忽略。请求宽度不调整为结束
于 `r_max_nm`。

Request 记录选择、输入来源、`r_max_nm`、`bin_width_nm`、帧范围和 Backend。非法参数、超过
一百万 sample、空选择和全 self pair 集合直接失败。CLI 和 GUI 默认值 `1.0 nm`、`0.002 nm`
只是输入默认值，不是物理推断。

## GROMACS Backend

`analysis_backend = gromacs` 时，存储曲线来自 `gmx rdf`。MDHelper 传入 `-bin`、`-rmax`、
`-ref`、`-sel`、`-o` 和可选 `-n`，再把 XVG 映射为 `radius_nm,g_r`。程序不传 `-cn`，也不
重算曲线。

完整帧范围使用原输入。其他范围使用 `gmx check` 和一次 `gmx trjconv -fr` 生成的精确子集，
不用 `gmx rdf -dt`。Provenance 记录命令、executable identity、版本、输出和帧。XVG 精度可能
使结果与进程内值存在小差异。

## 诊断与输出

第一壳层诊断平滑 RDF 副本，查找第一个显著峰和随后最小值，并以 high、medium 或 low
confidence 报告边界。该值始终需要用户确认，且不修改曲线或 `r_max_nm`。阈值见
[算法说明](../ALGORITHM.zh-CN.md)。

JSON 和 CSV 最多使用 15 位有效数字。基础结果不含 block size、standard error 或 uncertainty
band。本方法不估计平衡、自相关、收敛或有效样本量。

[验证报告](../validation/rdf-1.0.0.zh-CN.md)定义自动检查范围和限制。
