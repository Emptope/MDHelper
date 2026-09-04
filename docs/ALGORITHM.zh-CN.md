# MDHelper 算法说明

[English](ALGORITHM.md) | [简体中文](ALGORITHM.zh-CN.md)

本文定义 MDHelper 的工程实现行为。科学量和公式以带版本的
[方法文档](methods/README.zh-CN.md) 为准。

## 约定

- 存储距离使用 nm，时间使用 ps，体积使用 nm^3。径向绘图把距离转为埃。
- Backend 适配器只转换一次坐标和盒。Core frame 使用 NumPy `float64` array。
- 帧范围遵循零基 Python slicing：`start` 包含，`stop` 不包含，stride 相对 `start`。
  `stop = null` 表示轨迹末尾。
- 选择只解析一次，结果是有序零基原子索引。
- 坐标不做 unwrap、重建、对齐或拟合。
- `FrameAudit` 记录处理的帧索引、时间和数量。

## Backend 分派

```text
mdanalysis -> MDAnalysis loading + selection + frame handling + calculation
gromacs    -> GROMACS input + selection + frame handling + calculation
```

`auto` 按注册顺序尝试可用的完整 Backend。MDAnalysis 位于 GROMACS 之前。GROMACS 帧子集
还需要 `trjconv` 和 `check`。输入加载失败可以进入下一个完整 Backend。显式选择不回退。
Provenance 记录请求值和解析值。

MDAnalysis 适配器创建一个 Universe，保持原子顺序，把埃转为 nm，并将 molecule 映射为
`segid:residue_name:residue_id`。缺失或非有限 charge 保持 null。缺失 element 使用 atom name
回退，不执行化学推断。

## 选择

MDAnalysis 在存在 index 文件时使用 `NdxSelectionEngine`，否则使用静态 MDAnalysis
expression。注入的 engine 不能与 index 文件组合。GROMACS 引用 NDX 组；没有 NDX 时把原生
expression 传给 `gmx rdf`。

NDX 解析保持顺序，把一基编号转为零基索引，并拒绝缺失 header、重复 group、重复 atom、
选中的空 group、非法 token 和越界值。Group name 精确匹配且区分大小写。

MDAnalysis 拒绝依赖坐标的 expression，包括 `around`、`sphzone`、`sphlayer`、`isolayer`、
`cyzone`、`cylayer`、`point`、`prop` 和 `same x/y/z as`。

进程内选择记录 source、数量、有序索引 SHA-256、atom name、residue name、language 和 parser
version。NDX 还记录路径和文件 hash。GROMACS 记录原生 expression 或 group 及命令。

## 周期几何与径向网格

盒矩阵 `H` 的行向量为 `a`、`b`、`c`：

```text
V = abs(a dot (b cross c))
G = inverse(H)
h_i = 1 / norm(G[:, i])
r_limit = min(h_0, h_1, h_2) / 2
```

体积必须有限且大于 `1e-12 nm^3`。每帧要求
`r_max <= r_limit + max(1e-12, r_limit * 1e-10)`。

进程内路径调用 MDAnalysis `capped_distance` 计算三斜盒最小镜像距离。拓扑索引相同的 pair
被排除；等于 cutoff 的距离被保留。

请求宽度为 `d` 时：

```text
Q = max(1, round(2 * r_max / d))
B_rdf = floor((Q + 1) / 2)
B_cumulative = floor(Q / 2)
h = d / 2
```

RDF radius 为 `k*d`，cumulative radius 为 `(k+1)*d`。未匹配的末尾细 bin 被忽略。请求宽度
不调整为结束于 `r_max`。Radius 舍入到 15 位小数。RDF sample 不得超过 1,000,000 个。

## 进程内径向计算

Reference 数量为 `N_R`，selection 数量为 `N_S`，重叠数为 `O`，处理帧数为 `F`。每帧可用
非 self pair 数为 `N_R * N_S - O`，且必须为正。排除 self pair 不改变 RDF 归一化分母。

令 `H_(f,k)` 为重采样后的逐帧 count，`dV_k` 为 shell volume：

```text
D_S = sum_f (N_S / V_f)
g_k = sum_f H_(f,k) / (N_R * dV_k * D_S)

N_ref_obs = F * N_R
cumulative_number[k] = sum_(j=0..k) H_j / N_ref_obs
```

RDF 存储 `radius_nm,g_r`。累积 RDF 存储 `radius_nm,cumulative_number`。累计曲线表示每个
reference 原子的 selection atom 数，不把 atom contact 转成 molecule count。

## GROMACS 径向计算

默认帧范围把原输入传给一次 `gmx rdf`。RDF 使用 `-o`；累积 RDF 增加 `-cn`，并保留 RDF
输出用于壳层诊断。非默认范围用 `gmx check` 获取帧数，再用一次 `gmx trjconv -fr` 生成精确
XTC 子集。原 topology 仍作为 `-s` 输入。程序不用 `-dt`，因为它的采样起点与 Python slicing
不同。

`bin_width_nm` 和 `r_max_nm` 对应 `-bin` 和 `-rmax`。Pair selection、PBC、endpoint、
normalization 和 cumulative integration 由 GROMACS 决定。MDHelper 接受 radius 递增的有限
两列 XVG，映射到 result 契约，并记录所有命令。程序不重算曲线。

## 诊断与建议

第一壳层检测读取已完成的 RDF，不修改 RDF。算法至少需要 11 个点，使用不超过 11 的
Savitzky-Golay window，然后查找第一个符合条件的峰及其后的第一个最小值。

```text
peak prominence floor = max(0.05, 0.05 * max(smoothed_rdf))
minimum prominence floor = max(0.02, peak_floor / 2)
```

第一个合格峰及其后的第一个最小值定义建议边界。无法同时识别两者时结果不可用并产生警告。
可用边界都需要用户确认，且不修改 `r_max` 或其他结果。

Species 按 residue name 分组，molecule 按 molecule ID 分组。程序递归发现 Project 目录中的 `.itp`
文件提供角色证据：程序将 `[ moleculetype ]` name 与 residue name 匹配，并用 decimal arithmetic
累加每条 `[ atoms ]` record 的第 7 个字段。Net charge 大于 `+1e-6 e` 时建议 cation，小于
`-1e-6 e` 时建议 anion，舍入误差范围内则建议 solvent。完整匹配定义会产生角色建议，定义缺失
时不产生建议。建议需要用户确认且可以修改；角色不修改选择或参数。

所有 species 均匹配时，体系总电荷为每种 molecular charge 与检测到的 molecule 数量乘积之和。
体系总电荷的绝对值超过 `1e-6 e` 时产生用户警告。

## 绘图构造

- RDF 以埃为 X 轴，绘制 `g_r`，quantity 为 `g(r)`。
- 累积 RDF 绘制 `cumulative_number`，quantity 为 `Cumulative RDF`，Y label 为 `number`。
- Energy 以 ps 为 X 轴，绘制用户选择的 EDR term。

兼容的径向 series 使用 X domain 交集。RDF 使用主轴，累积 RDF 使用次轴。两个 Y 轴分别从
零开始，并基于可见 X 范围内的有限值计算。用户范围覆盖自动范围。

Residue-name 配色使用排序后的诊断 residue name。固定配色使用保存的 ID。次轴 series 使用
更深的虚线。标题必须去除首尾空白、可打印、单行且不超过 120 个字符。预览和导出使用相同
appearance state，不修改 result array。

## Provenance 与持久化

进程内输入按 4 MiB 分块计算 SHA-256。直接 GROMACS 运行不预先 hash 输入，记录解析路径和
命令。Provenance 记录 runtime 版本、平台、byte order、Backend 分派、输入、配置来源、角色
和参数决策。

Request、result、manifest 和 plot state 使用严格 schema 1。项目重定位只接受内容相同的输入。
提交结果时先校验 request 和输入身份，保存带指纹的 Integration stream，再写入并 hash result，
最后原子替换 manifest。Manifest 提交失败时删除未索引的新文件。加载时检查路径范围、hash、
身份和 schema。JSON 与 TOML 使用同目录临时文件和 `os.replace`。

## 外部工具、配置与 Job

可执行候选顺序为本次运行路径、配置路径、配置搜索路径、adapter 环境路径、`PATH`、adapter
路径。检测和执行使用参数向量、受限环境、输出捕获、超时和 `shell=False`。取消和超时终止
进程组，并在 run record 中保留已捕获输出。

`MDHELPER_CONFIG` 覆盖同目录 `config.toml`。配置通过校验后才原子替换。Template 按路径顺序
读取非空 ASCII 内容，并拒绝重复的不区分大小写 key。

Job 从 pending 进入 running，再进入 completed、failed 或 cancelled。取消点位于 hash chunk、
帧边界和进程轮询。单帧距离搜索可能延迟取消。

## 复杂度与变更检查

| 操作 | 最坏时间 | 额外内存 |
| --- | --- | --- |
| RDF 和累积 RDF | `O(F * N_R * N_S)` | `O(N_R + N_S + P + B)` |
| 文件 hash | 文件大小 | 4 MiB |
| 绘图模型 | Result point 数 | Result point 数 |

算法变更必须同步修改受影响的方法、schema、验证、测试和文档。变更必须保留或明确修改单位、
endpoint、PBC、self exclusion、selection identity、资源上限、取消和 provenance，且不得对
文件名、样例、species、测试或输出写特判。
