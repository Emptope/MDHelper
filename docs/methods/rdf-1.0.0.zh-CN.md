# 径向分布函数 — method 1.0.0

[English](rdf-1.0.0.md) | [简体中文](rdf-1.0.0.zh-CN.md)

状态：MDHelper 0.1.0 发布方法规范。

## 量与适用范围

对进程内后端，固定 reference 集合 A、selection 集合 B、第 `f` 帧和周期 cell 体积 `V_f`
下，RDF 第 `k` 个 sample 以 `k*d` 为中心，其中 `d` 是请求 bin width。首壳层为 `[0,d/2)`，
其余壳层为 `[(k-1/2)d,(k+1/2)d)`。MDHelper 统计有序 pair `(i,j)`：`i` 属于 A、`j`
属于 B、`i != j`，且最小镜像距离位于该壳层。令 `H_fk` 为 count、`Delta V_k` 为精确壳层
体积，则：

```text
g_k = sum_f H_fk / (|A| Delta V_k sum_f (|B| / V_f))
```

这是默认 `gmx rdf -norm rdf` normalization：逐帧原始 count 的平均值除以平均 reference
位置数、shell volume 和平均 selection number density。self pair 始终按 topology atom index
排除，但与 GROMACS 一致，排除项不会把 normalization 从 `|A||B|` 改为
`|A||B|-|A intersection B|`。存储、导出和绘图的 `g(r)` 不平滑。累积 RDF 是独立、显式
分析，不会隐式加到 RDF 结果。本方法面向每帧有有效 box 的三维周期 bulk 轨迹，不定义
slab、非周期、取向、质心、site-exclusion 或仅分子间 RDF。

## 选择、帧、单位和 PBC

Native 要求提供 `.ndx`，request 值是精确组名。MDAnalysis 有 NDX 时使用相同的精确组名，
否则接受静态 MDAnalysis expression。GROMACS RDF 使用精确 NDX 名；没有 NDX 时使用显式
GROMACS selection expression。帧采样始终遵循 Python slicing：`start` 是包含的零基索引，
`stop` 是不包含的结束位置，`stride` 相对 `start` 应用。

坐标和 radius 为 nm，`g(r)` 无量纲。位移使用三斜 cell vector 和 fractional minimum image。
每个处理帧中 `r_max_nm` 都不能超过最短垂直 cell height 的一半。缺失、奇异或零体积 box
直接报错。

backend 转成 nm 后直接消费坐标，不 unwrap、center、fit 或 align。结果记录实际首末帧索引、
时间和预处理记录。

request 与 `gmx rdf` 一致记录 `bin_width_nm`，不使用 bin count。进程内算法先建立
`round(2*r_max_nm/bin_width_nm)` 个半请求宽度的细 bin，再执行与 GROMACS 相同的两种重
采样。RDF radius 为 `0,d,2d,...`；细 bin 数为 `Q` 时 RDF sample 数为
`floor((Q+1)/2)`。请求宽度保持不变，不为了让末壳层落在 `r_max_nm` 而调整。RDF 重采样未
消费的末尾半 bin 会忽略。细 bin 左闭右开，恰好落在细 histogram 最终 edge 的距离不计入。

## GROMACS 后端

`analysis_backend = gromacs` 时，存储的 `g(r)` sample 直接来自 `gmx rdf`。MDHelper 传入 `-bin`、
`-rmax`、`-ref`、`-sel`、`-o` 和可选 `-n`，不请求 `-cn`，再把 RDF XVG 标准化为
`radius_nm,g_r`。进程内 grid、shell 重采样和 normalization 遵循相同的 GROMACS 默认定义；
外部分支的 PBC 与浮点实现仍由 GROMACS 决定。程序保持零基帧切片；默认全帧范围直接读取
原输入，有限抽样范围只使用一次精确转换子集，不用 `gmx rdf -dt`。provenance 记录命令
参数、可执行文件、版本、输出和帧审计；
MDHelper 不重算 GROMACS 曲线。由于不同 GROMACS 版本以有限精度写 XVG，Native float64
值与序列化值仍可能在实用容差内略有差异。

## 参数与第一壳层诊断

request 必须记录 `r_max_nm`、`bin_width_nm`、帧范围、`analysis_backend` 和完整选择来源。CLI/GUI 默认
`1.0 nm`、`0.002 nm` 只用于界面初始值，不能视为推断的物理事实。非法参数、超过一百万 bin、空
选择或只有 self pair 都失败。MDHelper 不推荐 `r_max`，也不静默调整请求。进程内后端逐帧
检查可靠最小镜像半径；GROMACS 后端把半径有效性交给 `gmx rdf`。

第一壳层建议只作诊断，不会自动改变其他分析：

1. 仅在诊断副本中把非有限值替换为零；
2. 使用不大于 11 的最大奇数 Savitzky-Golay window（最小 5），polynomial order 不高于 3；
3. 找 filter half-window 后第一个 prominence 至少为
   `max(0.05, 0.05 max(g_smooth))` 的峰；
4. 找至少隔一个 bin、prominence 至少为 `max(0.02, peak_floor/2)` 的随后最小值；
5. smooth peak-minus-minimum contrast >= 0.5 为 high，>= 0.2 为 medium，否则 low。

建议记录 peak/minimum、method、diagnostics、confidence 和
`requires_user_confirmation = true`。无法识别时返回 unavailable、原因和警告，不替换任意
cutoff。

JSON/CSV 最多 15 位有效数字，消除只来自二进制浮点表示的文本尾数，但不改 float64 计算。

## 确定性与统计范围

固定输入时，基础结果是所有所选帧的确定曲线，没有 block size、standard error 或
uncertainty band。本方法不估计平衡、自相关、statistical inefficiency、收敛、不确定度或
有效样本量。未来统计分析必须独立显式启用，先产生可审计 observable 时间序列，并保持
基础 RDF 不变。

## 验证契约

自动验证使用运行时生成、可手算的周期体系。期望 shell count 和 volume 独立构造，并用
`pytest.approx` 比较；重叠 selection 还验证 ordered-pair normalization 和 self exclusion。
覆盖范围与限制见匹配版本验证报告。
