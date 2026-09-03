# MDHelper 0.1.0 算法说明

[English](ALGORITHM.md) | [简体中文](ALGORITHM.zh-CN.md)

本文集中描述 MDHelper 当前实现中的算法。它既包含决定结果数值的算法，也包含会影响
可复现性的确定性工程算法。模块职责和依赖关系见 `docs/ARCHITECTURE.md`；方法的
发布定义见 `docs/methods/`；参考体系和容差见 `docs/validation/`。

本文只描述已实现行为。当前没有自动 `r_max` 推荐、动态选择、统计不确定度估计或结果
缓存算法。

## 1. 分类与事实来源

算法分为三类：

| 类别 | 内容 | 主要实现 |
| --- | --- | --- |
| 数值算法 | PBC、pair 距离、RDF、累计 RDF、第一壳层、energy 提取 | `analysis/radial/`、`analysis/rdf.py`、`analysis/cumulative_rdf.py`、`analysis/native.py`、`analysis/mdanalysis.py`、`analysis/gromacs/`、`analysis/energy.py` |
| 输入解释算法 | reader 分派、轨迹适配、选择解析、物种角色建议 | `backends/`、`io/ndx.py`、`services/selection.py`、`services/system.py` |
| 工程确定性算法 | 绘图分组/配色/范围、hash、项目提交、外部软件检测、job 取消 | `core/plotting/`、`services/provenance.py`、`project/`、`integrations/`、`runtime/`、`jobs/` |

若本文与代码或版本化方法文档不一致，发布前必须消除差异；不能把“代码就是事实”作为
长期保留文档漂移的理由。

## 2. 公共约定与符号

### 2.1 单位

- 内部坐标和距离统一为 nm；
- 内部时间统一为 ps；
- 盒体积为 nm^3；
- MDHelper GRO Reader 的坐标不缩放，因为 GRO 本身使用 nm；
- MDAnalysis 坐标和三斜盒矢量从埃除以 10 转成 nm；
- 径向绘图把 nm 转为埃，持久化结果仍保存 nm。

### 2.2 轨迹与选择符号

- `F`：实际消费的帧数；
- `R`：固定参考原子索引集合，大小为 `N_R`；
- `S`：固定 selection 原子索引集合，大小为 `N_S`；
- `O = |R intersect S|`：两选择重叠原子数；
- `H`：3 x 3 盒矩阵，三个盒矢量按行保存；
- `V_f = |det(H_f)|`：第 `f` 帧盒体积；
- `r_max`：RDF/CN 最大半径；
- `d_req`：请求的最大 bin width。

选择只在运行开始时解析一次。所有帧使用同一原子索引，因此结果不包含动态空间选择的
身份变化。

### 2.3 帧范围

`FrameRange(start, stop, stride)` 使用零基索引，`start` 包含而 `stop` 不包含；`stride` 的单位
是帧。

若范围内原本有多个可用帧，而 stride 最终只保留一帧，程序会拒绝该请求；显式单帧范围
仍然有效。

```text
start, start + stride, start + 2 * stride, ... < stop
```

`stop = null` 表示轨迹末尾。显式 `stop` 不得超过已知的轨迹总帧数；若没有任何帧满足范围
则失败。`FrameAudit` 记录实际帧数、首末索引和首末时间，包含请求值之外的运行事实。

### 2.4 坐标预处理

当前算法直接使用轨迹中保存并转换为 nm 的坐标：

- core frame 把坐标统一存为 `float64` NumPy 数组，reader 在 backend 边界一次完成格式和单位转换；
- 不 unwrap；
- 不做分子重构；
- 不对齐；
- 不拟合参考结构；
- 每一个 pair、每一帧独立使用三斜盒最小镜像。

## 3. 完整 Backend 分派

显式分析 Backend 对应一条完整策略：

```text
native     -> Native reader + NDX selection + Native frame/distance computation
mdanalysis -> MDAnalysis reader + MDAnalysis selection/frame/distance or Energy
gromacs    -> GROMACS input processing + GROMACS selection + RDF/CN or Energy
```

Auto 按优先级排列可用完整策略。径向请求只有在 GRO/GRO 加 NDX 时才先考虑 Native，随后
是 MDAnalysis，再随后是具备 `rdf` capability 的 GROMACS；GROMACS 帧子集额外需要
`trjconv` 和 `check`。Energy 先考虑
MDAnalysis，再考虑具备 `energy` capability 的 GROMACS。source 加载错误可以进入下一条
完整策略；显式请求不 fallback；同一次尝试不会组合不同 Backend 的组件。独立体系检查仍
使用 reader-only Auto：GRO/GRO 选择 Native，其他输入选择 MDAnalysis。provenance 记录解析
出的完整分析 Backend。

### 3.1 MDHelper GRO Reader

MDHelper GRO Reader 的处理顺序是：

1. 验证 topology 和 trajectory 都存在且扩展名为 GRO；
2. 从 topology 第一帧建立原子元数据；
3. 完整扫描 trajectory 计算帧数，并逐帧验证原子身份；
4. 分析时重新流式扫描 trajectory，只 yield 请求帧。

原子记录按 GRO 固定列读取：residue id `[0:5]`、residue name `[5:10]`、atom name
`[10:15]`，坐标分别为 `[20:28]`、`[28:36]`、`[36:44]`。`molecule_id` 为
`residue_name:residue_id`。标题中匹配 `t = number` 时使用该时间，否则以帧索引作为时间。

盒行有 3 个数时生成对角矩阵；有 9 个数时按 GRO 规定的交错顺序重排为三个行矢量。
其他数量失败。后续帧的原子数以及每个索引处的 residue id、residue name、atom name 必须
与 topology 一致。

该实现会在构造 source 时完整扫描一次、分析时再扫描一次，因此时间复杂度包含两次顺序
读取；优点是运行前已知 `n_frames` 且分析阶段保持低内存。

### 3.2 MDAnalysis 适配

MDAnalysis reader 创建一个 `Universe(topology, trajectory)`，然后：

1. 按 Universe 原子顺序建立零基 core `Atom`；
2. residue name/id 和 atom name 缺失时使用通用 fallback；
3. element 缺失或不可用时由 atom name 通用推断；
4. charge 只有在可读取且为有限数时保存，否则为 null；
5. `molecule_id = segid:residue_name:residue_id`；
6. 按 frame range 随机访问帧；
7. positions 与 triclinic dimensions 除以 10 转成 nm；
8. 缺少或退化盒矩阵最终在 `Box.validate()` 失败。

适配器只转换格式和单位，不执行 RDF/CN 公式。

### 3.3 通用元素推断

当格式不提供可靠 element 时，`backends/common.py` 从 atom name 中只保留字母并转大写。
没有字母时返回 `X`；前两个字母若属于 `BR`、`CA`、`CL`、`FE`、`LI`、`MG`、`NA`、
`SI`、`ZN`，返回首字母大写的二字母元素；否则返回第一个字母。

该 fallback 只处理通用元素名推断，不重建化学拓扑。后端提供的明确 element 优先，角色或分析
算法不得把推断 element 当作电荷证据。

## 4. 选择解析

### 4.1 分派规则

```text
if caller explicitly injects a SelectionEngine and also supplies index_file:
    fail
else if index_file is supplied:
    use NdxSelectionEngine
else if an engine is injected:
    use injected engine
else:
    use the default MDAnalysisSelectionEngine
```

多个表达式通过一次 `resolve_many` 解析，返回顺序与输入顺序一致。空选择始终失败。
该分派用于进程内分析。显式 GROMACS RDF/CN 有 NDX 时把组名写成 `group "name"`；没有
NDX 时把 request 值直接作为 GROMACS selection expression 传给 `gmx rdf`。

### 4.2 NDX 算法

1. 以 UTF-8 with optional BOM 读取全文；
2. 每行先删除分号后的注释并 trim；
3. `[ group ]` 开始新组，组名精确保存；
4. 数据行按空白切分为整数；
5. 每个整数必须处于 `[1, n_atoms]`；
6. 完成组时拒绝重复组名和重复原子号；
7. 将一基原子号减 1，得到内部零基 tuple；
8. 请求组名做精确匹配，未知或空组失败。

算法保持文件中的组顺序和组内原子顺序，不按数字重新排序。

### 4.3 静态 MDAnalysis 选择算法

服务先扫描表达式 token，拒绝坐标相关关键词 `around`、`sphzone`、`sphlayer`、
`isolayer`、`cyzone`、`cylayer`、`point`、`prop`，以及 `same x/y/z as` 模式。

随后根据 core atoms 构造一个坐标全零的轻量 Universe：使用 `molecule_id` 建 residue slot，
添加 names、types、elements、resnames 和 resids，再调用 `select_atoms()`。因为动态关键词已
拒绝，零坐标不会参与受支持选择的身份。

### 4.4 选择审计记录

每个进程内选择记录：

- 原表达式或组名；
- 原子数；
- 逗号连接的零基索引序列的 SHA-256；
- 去重排序后的 atom names 和 residue names；
- 选择语言和版本；
- NDX 模式下的 index path 与文件 SHA-256。

索引序列 hash 对顺序敏感，使同样成员但不同顺序仍可被区分。
直接 GROMACS 选择记录保留原 expression 或组名；选择解析和校验由记录在 Integration
command 中的 `gmx` 完成。

## 5. 周期性边界和距离

### 5.1 盒体积

三个行盒矢量为 `a`、`b`、`c`，体积为：

```text
V = abs(a dot (b cross c))
```

体积必须为有限数且大于 `1e-12 nm^3`。

### 5.2 可靠球半径

对一般三斜晶胞，最小镜像球壳可靠上限取最小晶胞垂直高度的一半。代码令：

```text
G = inverse(H)
h_i = 1 / norm(G[:, i])
r_limit = min(h_0, h_1, h_2) / 2
```

请求半径必须满足：

```text
r <= r_limit + max(1e-12, r_limit * 1e-10)
```

该检查对每一个实际帧执行。盒矩阵奇异或任一帧不满足时立即失败。

### 5.3 三斜盒最小镜像

对 reference 坐标 `x_r` 和 selection 坐标 `x_s`：

```text
delta = x_s - x_r
s = delta @ inverse(H)
s = s - round(s)
delta_mic = s @ H
distance_squared = delta_mic dot delta_mic
```

这里 `round` 由 NumPy `rint` 实现。pair 只有在原子索引不同且
`distance_squared <= cutoff^2` 时保留。self pair 由原子索引判断，距离是否为零不参与判断，
因此不同原子坐标重合仍是合法 pair。

### 5.4 空间索引和有界分块

轴对齐正交盒的大搜索使用周期 k-d tree。selection 按配置的 pair 上限分块建树，并先计算
每个 reference 的精确邻居数；随后按邻居数划分 reference，使每个稀疏距离结果不超过该
上限。小规模搜索和通用三斜盒搜索使用直接分块或周期性分数坐标分胞。倒易盒矢量给出各轴
上的保守分数坐标 cutoff，只有相邻且非空的分胞可能包含保留 pair。候选 pair 仍使用 5.3 节
的三斜盒最小镜像公式。两种空间索引都不改变 pair 身份和与顺序无关的 histogram 结果。

RDF/CN 邻居搜索的 cutoff 严格等于 request 中由用户或模板设置的 `r_max`。空间索引不会
另行推断、缩小或调整这个 cutoff。

若配置的 pair 上限为 `M`，每个候选块的目标和参考 chunk 大小为：

```text
selection_chunk = max(1, min(N_S, floor(sqrt(M))))
reference_chunk = max(1, floor(M / selection_chunk))
```

直接路径的每个临时距离矩阵至多约有 `M` 个元素。所有路径只 yield 通过 cutoff 的
reference slot、selection slot 和距离。局部 cutoff 不再枚举完整 `N_R x N_S` 笛卡尔积；
不适合空间索引时仍不构造完整距离矩阵。

## 6. 进程内径向网格

进程内网格复现 `gmx rdf` 的半宽 histogram 和重采样。请求宽度为 `d` 时：

```text
Q = max(1, round(2 * r_max / d))
B_rdf = floor((Q + 1) / 2)
B_cn = floor(Q / 2)
h = d / 2
```

`Q` 是宽度为 `h` 的细 bin 数。RDF 第 `k` 个 sample 位于 `k*d`；首壳层为 `[0,d/2)`，
其余壳层为 `[(k-1/2)d,(k+1/2)d)`。壳层体积为：

```text
dV_0 = (4 * pi / 3) * (d/2)^3
dV_k = (4 * pi / 3) * ((k+1/2)^3 - (k-1/2)^3) * d^3, k > 0
```

CN 第 `k` 个 sample 位于 `(k+1)*d`，合并细 bin `2k` 和 `2k+1`。相关重采样会像
GROMACS 一样忽略末尾无法配对的细 bin。请求宽度不会为了让最后 sample 落在 `r_max` 而
调整。radius 舍入到小数点后 15 位以稳定序列化，RDF sample 数不能超过 1,000,000。

## 7. 进程内 RDF 算法

### 7.1 Pair 定义

RDF 使用有序 reference-selection pair。每帧可能的非 self pair 数为：

```text
N_pair = N_R * N_S - O
```

其中 `O` 是 reference 和 selection 集合的交集大小。如果 `N_pair <= 0`，请求失败。该数只
用于有效性检查和诊断；与 GROMACS 一致，排除 self pair 不会把 RDF normalization 从
`N_R*N_S` 改成 `N_pair`。

### 7.2 逐帧累积

对每个请求帧 `f`：

1. 检查取消；
2. 验证 `r_max` 不超过该帧可靠半径；
3. 分块计算最小镜像距离；
4. 累积半宽细 histogram，再重采样为 RDF count `H_(f,k)`。

定义：

```text
H_k = sum_f H_(f,k)
D_S = sum_f (N_S / V_f)
```

### 7.3 归一化

最终 RDF 为：

```text
g_k = H_k / (N_R * dV_k * D_S)
```

该式等价于 GROMACS 依次对逐帧原始 count 求平均，再除以平均 reference 位置数、shell
volume 和平均 selection number density。它逐帧使用实际盒体积，适用于盒体积变化。

输出数据是 `radius_nm` 与 `g_r`。结果还记录实际 bin width、请求 bin width、帧审计、
原子数量、每帧可能 pair 数、选择解析和第一壳层诊断。

## 8. 进程内累积 RDF 算法

CN 将同一个半宽细 histogram 重采样为 `[k*d,(k+1)*d)` 区间，不使用 RDF 的理想气体
归一化。
参考原子观测总数为：

```text
N_ref_obs = F * N_R
```

第 `k` 个 sample 的累计数为：

```text
N_k = (sum_(j=0..k) H_j) / N_ref_obs
```

该值在 `(k+1)*d` 处输出，语义是“每个 reference 原子周围从 0 到该上边界范围内，平均有
多少 selection 原子”。当前实现直接
累计离散 pair counts，不通过数值积分 `4*pi*r^2*rho*g(r)` 再计算；两者在理想离散条件下
相关，但代码路径和浮点行为不同。完整曲线内部字段为 `cumulative_number`；UI 将其显示为
`Cumulative Coordination Number (CN)`，纵轴标签为 `Coordination number`。仅在壳层边界取得的
单值使用 `coordination_number`。

### GROMACS RDF/CN 后端

显式 `gromacs` request 不用上述公式作为曲线数据源。默认 `0:end:1` 范围把所选 topology
和 trajectory 直接传给一次 `gmx rdf`。RDF request 只使用 `-o`；cumulative RDF request
额外使用 `-cn`，并保留 RDF 输出供共同的第一壳层诊断使用。非默认范围把零基帧索引
转换为一次 `gmx trjconv -fr` 接受的一基 NDX 条目，生成精确 XTC
子集，`gmx rdf -s` 仍使用原 topology。每个非默认范围先用 `gmx check` 获取帧数并校验
显式 stop，不把完整轨迹展开为另一种坐标格式。`-dt` 按绝对时间网格取样，Python
stride 按相对 `start` 的索引取样，因此两者不能互换。

request 的 `bin_width_nm`、`r_max_nm` 分别传给 `-bin`、`-rmax`。该分支的 pair selection、
PBC、grid endpoint、RDF normalization 和 cumulative integration 均由 GROMACS 决定。
MDHelper 严格解析两列有限数值且 radius 递增的 XVG，映射成 `radius_nm` 与 `g_r` 或
`cumulative_number`，应用共同的第一壳层诊断；记录全部 metadata inspection、conversion 与 `rdf`
Integration run。程序不重算或替换曲线。

## 9. 第一配位壳诊断

该算法只消费已完成的 RDF 数组，不改变 RDF 或 CN。

### 9.1 预处理

1. 若点数少于 11 或不存在有限 RDF 值，返回 `insufficient_data`；
2. NaN、正负无穷替换为 0；
3. window 为不超过 11 的最大可用奇数，且至少为 5；
4. Savitzky-Golay polynomial order 为 `min(3, window - 2)`；
5. 生成平滑序列，仅供峰谷检测。

### 9.2 峰和谷

峰 prominence 下限为：

```text
p_peak = max(0.05, 0.05 * max(smoothed_rdf))
```

在平滑序列上用 `find_peaks`，只接受索引不小于 `max(2, window // 2)` 的峰，取第一个。
若没有则返回 `no_resolved_first_peak`。

随后在负平滑序列上找最小值，prominence 下限为：

```text
p_min = max(0.02, p_peak / 2)
```

只接受位于 peak index + 1 之后的最小值，取第一个。没有则返回
`no_resolved_minimum_after_peak`，但仍报告已发现的第一峰。

### 9.3 置信度

令：

```text
contrast = smoothed_peak - smoothed_minimum
```

- `contrast >= 0.5`：high；
- `0.2 <= contrast < 0.5`：medium；
- `contrast < 0.2`：low。

可用诊断始终带 `requires_user_confirmation = true`。low 产生检查曲线警告；不可用产生
没有可靠第一最小值的警告。CN 分析若得到 minimum index，会把该 index 的离散 CN 值附加
到诊断中。

该诊断不包含误差分析，也不自动修改 cutoff 或 `r_max`。

## 10. 物种角色建议算法

角色建议按 residue name 把原子分成 species，再按 `molecule_id` 分子化。它不查看文件名，
也不针对 `SOL`、`Li` 等名称写特判。

### 10.1 电荷证据

对一个 species 的每个 molecule：

1. 若任一原子 charge 缺失，则该 species 的电荷证据不完整；
2. 否则求 molecule net charge；
3. 容差固定为 `0.25 e`。

决策规则：

```text
all molecular charges > +0.25 e  -> cation, high confidence
all molecular charges < -0.25 e  -> anion, high confidence
all abs(charges) <= 0.25 e        -> neutral candidate
otherwise                         -> unavailable
```

### 10.2 中性物种

在所有中性候选中：

- 若存在唯一 molecule count 最大者，建议它为 solvent，low confidence；
- 并列最大或非最大中性 species 都不自动决定角色；
- 候选角色仍包含 solvent、additive、polymer、surface、other 等供用户确认。

inspection summary 显示 molecule count、atoms-per-molecule 取值、charge 是否完整、charge
range、mean charge、方法、理由、置信度和候选角色。持久化 request 只保留选择来源、建议角色、
置信度和逐 species 证据；最终角色只存于 `request.species_roles`，不复制到 result provenance。
角色不改变原子选择、半径、bin 或数值公式。

## 11. 绘图构造算法

### 11.1 从结果生成序列

- RDF：x 从 nm 转埃，y 为 `g_r`，quantity 为 `g(r)`，domain 为 `radial_distance`；
- cumulative RDF：x 从 nm 转埃，y 为 `cumulative_number`，quantity 为 `N(r)`，同一 domain；
- energy：x 为 `time_ps`，每个显式选择的 EDR term 形成一条序列。

RDF 的 axis order 为 0，CN 为 1。组合时最小 axis order 成为 primary，因此 RDF+CN 图中
RDF 使用左轴、CN 使用右轴。不同 domain 或不兼容横轴形成不同 panel。

### 11.2 结果合并与标签

结果按 `(plot kind, domain, x label)` 分组；没有 domain 时还比较 y labels、title 和参考线。
自定义 label 在单序列模型上替换原 label，多序列模型使用 `custom: original`。同一 axis、
quantity、label 再次出现时依次加 `(2)`、`(3)`，保证图例唯一。

非空的持久化标题覆盖该分组绘图的自动标题。GUI 修改标题时，将标题同步到当前绘图中所有
可见来源序列。后续分组若合并了原本具有不同标题的序列，按输入顺序采用第一个非空标题，
保证结果确定。标题必须是去除首尾空白的单行可打印字符串，最长 120 个字符；空标题恢复
自动标题。

经过校验的外观状态控制图例和网格可见性、图例位置、线宽以及各类字体大小。主轴和 step
序列直接使用所选线宽，次轴序列使用该线宽的 90%，参考线使用 50%。预览与导出渲染器消费
同一外观状态，且不会修改不可变结果数组。

### 11.3 Residue name 配色

RDF/cumulative RDF 使用 selection 诊断中的 `residue_names`。算法：

1. 只保留非空字符串；
2. 去重；
3. 字典序排序；
4. 用 `|` 连接；
5. 无有效诊断时回退到 selection/label。

按序列首次出现的 residue key 分配调色板索引，相同 key 复用颜色。颜色表是固定 17 色序列，
类别分配有固定顺序，因此同一组有序序列的颜色确定。

`Fixed color` 直接使用 `PlotSelection.color_id` 查固定颜色表。当前没有 Atom name 配色。

secondary axis 颜色的 RGB 每个通道乘 `0.5` 并取整，同时使用虚线；这使 RDF/CN 同选择
既保持颜色关系又可辨别量纲。

### 11.4 自动坐标范围

仅 `radial_distance` domain 计算共同自动横轴。对每条序列求 `[min(x), max(x)]`，然后：

```text
lower = max(all minima)
upper = min(all maxima)
```

若 `lower >= upper` 或任一 x 非数值，则不设置共同自动范围。否则自动范围左端在
`lower >= 0` 时扩展为 0，右端为 `upper`。用户给出的单侧/双侧 x limits 覆盖相应自动端点。

绘制 y 前只选取当前 x range 内的数据。径向 primary/secondary y 轴分别从 0 开始，顶部为：

```text
1.0,                if no positive finite maximum
1.05 * finite_max,  otherwise
```

RDF 的 `g(r)=1` 参考线也参与 primary 最大值。用户 y/y2 limits 最后覆盖自动端点。GUI 中
配色和范围变化立即重绘，没有额外 Apply 阶段。

## 12. 内容指纹与 provenance

### 12.1 SHA-256

进程内分析输入每次读取 4 MiB，逐块更新 SHA-256。开始前和每块读取前检查取消事件；每块
后报告已处理字节和总大小。topology 与 trajectory 指向同一路径时只 hash 一次。NDX 等
附加输入按相同规则加入。直接 GROMACS 分析跳过原生命令启动前的输入 hash，记录解析输入
路径和完整 Integration command。

选择索引 hash 与文件 hash 是不同层次：前者标识解析出的有序原子索引，后者标识整个输入
文件内容。

### 12.2 Provenance 组合

分析 provenance 由以下确定性字段组合：

- MDHelper、Python、MDAnalysis、NumPy、SciPy、Matplotlib 版本；
- platform 和 byte order；
- 请求及解析出的完整 Backend；
- 输入角色到 path 的映射，以及存在预先 hash 时 path 到 SHA-256 的映射；
- 配置来源；
- 角色状态与确认映射；
- 参数决策记录。

应用用例在 source 加载后生成 provenance，因此同时记录用户请求的 `auto` 和实际 adapter
的 Backend name。

## 13. 项目算法

### 13.1 创建、打开与 manifest 校验

创建项目时先解析 root，记录 topology/trajectory/可选 index 的 path 与 hash，校验角色，
然后构造 schema 1 manifest。默认拒绝已有 project 和非空目录；app 的 `ensure()` 用例在
GUI 自动建立轨迹目录项目时显式允许非空目录。随后创建 `results`、`results/data`、
`results/runs`、`figures`、`cache` 目录并原子写 `mdhelper-project.json`。

打开项目时：

1. 读取并解析 JSON；
2. 严格验证顶层、input、紧凑 analysis 索引和 plot；
3. 严格解析 plot state，不补旧字段或迁移旧状态；
4. 补齐项目目录；
5. 默认解析并验证所有记录输入的 hash。

### 13.2 输入记录与重定位

记录输入时只保存一个 path 和 SHA-256。当相对 project root 的路径可表示时保存
relative path；Windows 跨卷时保存 absolute path。恢复时：

1. relative path 与 `project_root` 组合，absolute path 直接使用；
2. 候选必须是文件；
3. 启用验证时，内容 hash 必须等于记录值。

显式 relocate 会先对新文件建立记录，再要求新旧 hash 相同。更换分析输入必须创建新项目，
不能用 relocate 掩盖。

### 13.3 结果提交

1. 校验 result 和 request；
2. 要求 result 内嵌 request 与提交 request 完全相等；
3. 要求 result provenance path 与 request path 一致；
4. 对已有 project input 复用其记录，对新增 input 建立 path 与 hash 记录；
5. result provenance 提供 hash 时要求它与 project input 一致；
6. 拒绝重复 `analysis_id` 和已存在结果路径；
7. 将每条 integration run 的 stdout/stderr 按 analysis ID 和 run 顺序原子写入
   `results/data/` 下的 `.out`/`.err` 文件，并计算 SHA-256；
8. 在待持久化 run record 中用 SHA-256 替换流正文，不保存流路径；
9. 原子写一份完整结果到 `results/data/<analysis_id>.json`；
10. 对完整结果计算 SHA-256；
11. 将 analysis ID、分析类型、提交时间、hash 和新 input 记录加入 manifest；结果路径由 ID 推导，request 和 method 只保存在完整结果中；
12. 严格校验并原子写 manifest；
13. 第 12 步失败时删除第 7、9 步新建的未索引流文件与结果文件。

每个结果条目都必须包含 `result_sha256`。加载结果时先确保 manifest 路径位于
`results/data/` 内，再检查文件存在、校验内容 hash；随后按 analysis ID 和 run 顺序定位
同目录流文件，校验 SHA-256 并恢复内存中的 stdout/stderr，最后用
`AnalysisResult.from_dict()` 重新解析。manifest 不保存 integration preference 或
integration run 历史；独立 run 保存在 `results/runs/`。

### 13.4 原子 JSON 写入

规范 JSON 写入目标同目录的 `.<name>.tmp`，成功后用 `os.replace()` 原子替换。异常时删除
临时文件。配置和导出采用相同总体策略。当前没有显式 `fsync`，因此避免半文件主要依赖
同文件系统原子替换；突然断电后的持久性仍取决于操作系统和文件系统。

## 14. 外部工具算法

### 14.1 候选发现与选择

候选优先级依次为：

1. 本次运行显式 executable；
2. 用户配置 executable；
3. 用户配置 search paths；
4. adapter 声明的环境候选；
5. adapter 候选名在 `PATH` 中的解析结果；
6. adapter 声明的候选路径。

工具被配置为 disabled 时仍允许本次运行显式 executable，其余自动候选不加入。候选先转成
规范路径去重，但保留首次出现的 precedence。每个候选都探测，选择时取 precedence 最小的
available detection 记录。

GROMACS 环境候选为 `MDHELPER_GROMACS`，以及 `GMXBIN` 下的平台候选名；PATH 候选是
Windows 的 `gmx.exe`/`gmx_mpi.exe` 或其他平台的 `gmx`/`gmx_mpi`。

选出第一个 available detection 记录后，app 才检查项目的 `required_capabilities`；若缺少则失败，
不会继续搜索较低优先级但能力更全的候选。manifest 中的 `preferred` 当前被保存和校验，
但不参与 executable 排序。

### 14.2 探测

1. 解析相对名或绝对路径；
2. 要求是文件，非 Windows 还要求 executable bit；
3. 构造只含平台基础键和 adapter 允许键的子环境；
4. 以 `shell=False`、捕获 stdout/stderr 和配置超时运行版本参数；
5. GROMACS 要求退出码 0 且输出包含身份文本，再提取版本；
6. 运行 capability 参数并解析命令表；
7. 返回 available、version、capabilities、source、precedence 和失败诊断。

### 14.3 执行、取消和超时

正式运行使用 `[executable, *arguments]`、显式 cwd、受限 environment 和 `shell=False`，
按调用需求使用 `stdin=DEVNULL` 或受控文本输入，并捕获文本输出。参数包含 NUL 时拒绝。

独立 pipe reader 在线程中持续读取 stdout/stderr；任务循环以不超过 0.25 s 的间隔发布已捕获
输出和耗时，并检查进程状态：

- cancel event 被设置：终止完整进程组并进行有界等待；构造 cancelled run record 后抛
  `JobCancelled`；
- 总 timeout 到达：强制终止完整进程组，构造 timed_out record 后抛 backend error；
- 自然结束：exit code 0 标为 completed，否则标为 failed，并返回 record。

run record 包含 argv、cwd、受控环境摘要、stdout/stderr、开始时间、耗时、退出码、状态和
显式输出文件的 SHA-256。非零退出本身不丢失 record。

## 15. 配置与模板算法

### 15.1 配置路径

```text
if MDHELPER_CONFIG is set:
    use it
else:
    use config.toml next to the executable
```

冻结程序的 bootstrap 会在应用服务构造前选定同目录配置，但不会覆盖用户已经
设置的 `MDHELPER_CONFIG`。

### 15.2 配置保存

`save_config` 将 dataclass 转为 TOML 写入临时文件，对临时文件执行完整 `load_config`
校验，再用 `os.replace` 提交。校验拒绝未知 table/field、错误类型、非有限或越界数值。

`initialize_config` 写内置 ASCII 模板并原子替换；除非显式 force，否则不覆盖已有文件。

### 15.3 模板发现

从模板 root 递归遍历文件并排序，跳过任一路径段以点开头的隐藏文件。内容必须以 ASCII
解码且非空。相对路径去扩展名形成 case-insensitive key；第一路径段形成 category；文件
stem 的 `_`/`-` 替换为空格后 title case 形成 title。重复 key 失败。

## 16. 任务状态、进度和取消

`JobRunner.submit()` 建立 pending handle 和 cancel event，将 work 放入默认单 worker
executor。worker 开始时设 running，应用服务返回时设 completed；异常时，如果 cancel event
已设置则设 cancelled，否则设 failed，同时保存异常。

进度回调更新 handle 的 current、total 和 message。GUI 每 100 ms 在主线程读取 handle；
CLI/TUI 的 `run_sync()` 直接调用同一应用分析用例。

取消通过状态信号表达，Python 线程在以下协作点停止：

- provenance hash chunk；
- 每个分析帧；
- 外部进程轮询。

pair 分块迭代自身当前没有单独的 cancel 参数；取消通常在下一帧开始或其外层调用点生效。
因此 `max_pairs_per_chunk` 只约束临时内存，不保证改善取消响应；一个超大帧可能延迟取消。

## 17. 契约解析和验证

`AnalysisRequest.from_dict()` 只接受 0.1.0 当前 schema：它按 `analysis_type` 分派为
`RadialRequest` 或 `EnergyRequest`，两者不共享无关字段。它拒绝未知或缺失字段，
仅为径向请求构造 `FrameRange`，并执行各自的语义校验。结果解析拒绝未知字段、
非有限 JSON 数、非法时间、错误 schema/type、无效内嵌 request 和分析类型不一致。

`PlotState` 同样严格要求当前 scheme、颜色编号和主/次纵轴范围字段。0.1.0 是最初开发
版本，不迁移开发期旧字段或旧绘图状态。

## 18. 复杂度与资源上界

令平均帧数为 `F`，reference 原子数为 `N_R`，selection 原子数为 `N_S`，bin 数为 `B`，pair chunk
上限为 `M`：

| 算法 | 最坏时间量级 | 主要额外内存 |
| --- | --- | --- |
| RDF/累积 RDF pair 遍历 | 最坏 `O(F * N_R * N_S)`；k-d tree 或局部分胞按候选 pair 缩减 | `O(N_R + N_S + M + B)` |
| GRO source 构造 | `O(F * N_atoms)` 扫描 | `O(N_atoms)` 每帧 |
| 文件 SHA-256 | `O(file bytes)` | 4 MiB chunk |
| 绘图模型 | `O(result points)` | `O(result points)` |

chunking 限制临时距离矩阵。轴对齐正交盒的大搜索使用周期 k-d tree，先分块建立 selection
tree 并计算精确邻居数，再按邻居数约束 reference 块，使稀疏距离结果不超过 `M`。三斜盒
继续使用周期分胞；两种索引都在局部 cutoff 下减少候选 pair，但最坏时间复杂度仍不变。
后续优化若改变 pair 枚举方式，必须保持 self exclusion、三斜 PBC、cutoff 边界和结果容差。

## 19. 算法修改检查表

- 是否更新对应 `method_version`，以及 request/result/schema？
- 公式、单位、端点包含关系和浮点容差是否写清？
- 变盒、三斜盒、重叠选择、自配对和空数据是否覆盖？
- 算法是否仍按显式帧范围和固定选择运行？
- 是否保留输入、选择、参数和实际 backend 的 provenance？
- 内存上限和取消响应是否仍可接受？
- 诊断是否与原始结果数组分离？
- 是否存在按文件名、样例名、物种名、测试名或特定输出文本写的特判？
- 方法文档、验证文档、架构文档和设计目标是否同步？

数值算法的正确性、工程算法的确定性和持久化算法的失败原子性共同构成可复现性。任何一层
出现隐式 fallback、无记录修正或未验证写入，都会使数值本身即使正确也难以审计。
