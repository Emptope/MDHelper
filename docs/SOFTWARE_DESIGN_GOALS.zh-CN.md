# MDHelper 0.1.0 软件设计目标

[English](SOFTWARE_DESIGN_GOALS.md) | [简体中文](SOFTWARE_DESIGN_GOALS.zh-CN.md)

本文规定当前版本必须保持的工程性质及其验收方式。`ARCHITECTURE.md` 回答“系统现在如何
组成和运行”，`ALGORITHM.md` 集中说明“数据具体怎样计算和作出确定性决策”，本文回答
“修改系统时必须保护什么、怎样判断完成”。三者都以仓库现状为准，不把路线图或尚未
实现的功能写成当前能力。

0.1.0 是最初开发版本，不承担历史 API、文件格式或行为兼容义务。需要改变错误的早期设计
时，应直接更新实现、契约、schema、文档和测试，禁止叠加兼容分支。版本号仍必须在所有
发行入口保持一致。

## 1. 产品任务与范围

MDHelper 的当前任务是把轨迹或 EDR 输入、原子或 energy term 选择、分析计算、结果解释、
项目保存和多前端操作组成一个可复现的完整闭环。分析类型数量不作为产品目标。

0.1.0 的闭环包含：

```text
load trajectory or EDR input
  -> inspect system/selections or discover Energy terms
  -> confirm species roles when applicable
  -> construct explicit AnalysisRequest
  -> run RDF / CN / energy
  -> validate AnalysisResult
  -> export and/or commit to project
  -> reload, inspect, and plot the same result
```

支持的产品形态是 Linux TUI/CLI 和 Windows TUI/CLI/GUI。Native、MDAnalysis 和可选
GROMACS 都是显式、可审计且互不混用的完整分析流水线；request 与结果必须记录请求及解析
出的 Backend，不能隐藏调用。

## 2. 目标优先级

发生取舍时使用以下顺序：

1. 方法定义正确且有验证证据；
2. 结果可复现、输入和决策可审计；
3. 数据与项目不会因失败或取消而损坏；
4. 三个表现层共享同一业务和分析语义；
5. 大轨迹下内存、并发和取消行为有界；
6. 界面清晰、平面化且不依赖小字提示；
7. 扩展新分析或后端时不破坏现有边界；
8. 最后才是便利性和功能数量。

如果一种便利功能会隐式改变选择、采样或分析参数，应优先选择显式、可审计的行为。

## 3. G1：完整垂直切片

### 目标

每个发布分析都必须从三个表现层进入同一应用用例，经过实际所选后端，形成可校验结果，
并能导出或保存到项目。只有界面、占位菜单或未接线函数不算实现。

### 当前机制

- `AnalysisRequest` 集中表达输入、选择、参数和帧采样；
- `ApplicationService` 是表现层唯一业务门面；
- `AnalysisRegistry` 把分析名绑定到实现；
- `AnalysisResult` 是项目、导出和绘图的共同输入；
- CLI/TUI 使用同步 job 语义，GUI 通过 `JobRunner` 后台执行同一用例。

### 验收标准

- RDF、CN、energy 都能由共享用例端到端运行；
- 前端不直接导入 `analysis` 或 `backends`；
- 同一请求在不同入口得到数值等价的数据字段；
- 失败路径返回结构化错误，不留下伪成功结果。

## 4. G2：每种方法只有一个事实来源

### 目标

公式、单位、PBC、帧采样和归一化不能在 CLI、GUI、导出器或多个分析文件中各自实现。
算法代码应能在无界面的单元测试中直接验证。

### 当前机制

- RDF 和 CN 共用 `analysis/radial.py` 的 pair histogram；
- PBC、可靠半径、分块距离、帧审计在 `analysis/common.py`；
- energy 的 MDAnalysis 与 GROMACS 后端共用严格结果契约和 App term 发现用例；
- `docs/methods/` 记录公式，`docs/validation/` 记录独立期望和容差；
- 内部距离为 nm、时间为 ps，显示单位转换在绘图边界完成。

### 验收标准

- 正交盒和三斜盒最小镜像均有测试；
- 每帧检查 `r_max`，不以首帧盒子替代整条轨迹；
- bin 数、边界、shell volume 和归一化与方法文档一致；
- 参考/目标选择重叠时自配对语义明确；
- 改公式时同步修改方法、验证数据和测试。

## 5. G3：稳定的核心契约与单向依赖

### 目标

领域对象和协议独立于 Qt、命令解析、MDAnalysis Universe、文件布局及外部进程，使分析
代码可以替换 I/O 后端，表现层也可以独立演化。

### 当前机制

- `core` 定义 request/result、Atom/Frame/Box、轨迹/选择协议、错误和绘图模型；
- `backends` 将 GRO 和 MDAnalysis 转换为 core 类型；
- `services` 组合后端但不把第三方对象泄漏给 app；
- `app` 编排用例；CLI/TUI/GUI 只依赖门面和允许展示的 core 类型；
- 架构测试检查 core 反向依赖、表现层互相依赖和表现层直连分析后端。

### 验收标准

- `core` 不导入其他 `mdhelper` 外层包；
- GUI、CLI、TUI 不彼此导入；
- 包根没有业务模块；
- 新后端通过协议接入，不在算法中增加格式判断；
- 新前端不复制项目提交、选择解析或分析计算。

## 6. G4：显式选择、参数和采样

### 目标

结果所依赖的每个选择、半径、bin、cutoff 和帧范围都应在请求或已记录的模板中可见。
程序不得根据文件名、体系名或测试样例偷偷改变它们。

### 当前机制

- NDX 组和静态 MDAnalysis 表达式都解析为固定、零基索引；
- 动态选择关键词被拒绝；
- `r_max`、bin width、cutoff、start/stop/stride 是请求字段；
- 选择来源、组/表达式、索引 hash、原子名和残基名写入诊断/provenance；
- GUI/TUI 在运行前展示最终配置。

### 验收标准

- 空选择、越界索引、重复 NDX 组或非法帧范围在计算前失败；
- 请求 JSON 足以解释一次运行的分析配置；
- 没有运行前自动 `r_max` 推荐或静默修正；
- 模板展开后仍形成普通、可校验请求；
- 任何默认值都有单一声明位置和测试。

## 7. G5：建议必须可解释且不改变事实

### 目标

辅助诊断可以降低配置成本，但必须与用户选择和原始数据分离。建议无法确定时应明确标记
不可用，不得伪造高置信答案。

### 当前机制

当前只有两类建议/诊断：

- 物种角色建议依据分子净电荷和数量，使用 0.25 e 容差；模糊结果需要用户确认；
- 第一配位壳诊断依据已计算 RDF 的平滑峰谷，只作为运行后解释信息。

角色不改变原子选择或算法。第一壳层诊断不改变 RDF/CN 数组，`r_max` 始终由用户决定。
当前没有通用 `ParameterRecommender`。

### 验收标准

- 规则、证据、置信度和不可用原因可被记录；
- 不按残基名、原子名或特定体系写硬编码角色规则；
- 平滑数据只用于诊断，不覆盖导出的原始曲线；
- 建议失败不导致主分析伪失败，除非该信息是显式必需输入；
- 用户覆盖或确认进入 provenance。

## 8. G6：版本化、严格且自描述的结果

### 目标

结果不仅是一组数组，还必须说明分析方法、单位、选择、帧、输入和诊断。未知或损坏字段
应尽早失败，不能被悄悄忽略。

### 当前机制

- request/result/project 都使用 schema 版本 1；
- 径向请求和 Energy 请求使用互斥字段，不序列化另一分析类型的参数；
- core 解析器和 project Python schema 严格检查字段；
- `schemas/` 发布对应 JSON Schema；
- JSON 导出保留完整契约，CSV 提供稳定表格视图；
- RDF/CN/energy 分别验证必需数组和长度关系。
- 结果不保存尚未实现的 uncertainty 空对象或恒为 completed 的状态；project analysis 条目只保存 ID、类型、提交时间和内容 hash。

### 验收标准

- 未知字段、缺少字段、非法枚举和数组长度不一致均失败；
- 运行时校验器、core 序列化器和 JSON Schema 同步；
- JSON 往返不改变语义；
- CSV 精度足以复核，当前为 15 位有效数字；
- 展示单位转换不写回结果数据。

0.1.0 不要求兼容旧 schema。若修改结构，应一次性更新所有生产者、消费者、测试和文档，
不得长期保留两套含义相近的字段。

当前解析器只接受 0.1.0 字段；pre-0.1 request 字段和旧绘图状态直接失败，不规范化、
迁移或保留迁移分支。

## 9. G7：完整 provenance 与可复现性

### 目标

工程师应能从结果判断“什么输入、什么代码环境、什么选择和参数产生了这些数据”，并能
检测输入或结果文件被替换。

### 当前机制

- 输入文件和结果文件使用 SHA-256；
- 记录 MDHelper、Python、关键依赖和平台版本；
- request、diagnostics 和 provenance 共同记录请求及解析出的 Backend、选择证据、物种角色、参数决策和帧审计；
- 项目移动后只按相同 hash 重连输入；
- 每个项目结果条目都必须包含结果 hash；项目加载时重新验证全部 hash 和结果契约。

### 验收标准

- 路径相同但内容变化可以被检测；
- 路径变化但内容相同可以安全恢复；
- Auto 最终选中的完整 Backend 可追踪；
- 实际消费帧数与请求范围可核对；
- 外部工具若参与辅助流程，其身份、版本、argv、退出码和输出 hash 可记录。

## 10. G8：项目持久化具有失败原子性

### 目标

崩溃、磁盘错误、非法 manifest、取消或结果篡改不能产生看似完整但不可验证的项目。

### 当前机制

- JSON 和配置使用同目录临时文件加原子替换；
- 结果先独立写入并 hash，随后原子更新 manifest；
- manifest 更新失败时回收未索引结果；
- 读取时阻止路径逃逸并重新校验 hash/schema；
- manifest 打开时按当前 schema 1 严格校验，不改写不兼容或缺字段的内容。

### 验收标准

- 任意写入失败后，旧版本仍可打开或失败原因明确；
- 项目不能引用根目录外的结果文件；
- 未完成任务不会进入 manifest；
- 手工修改结果后必须明确加载失败；
- `cache/` 只保存可重建的 XDR 帧偏移等性能数据，不保存分析结果；删除后重建且不改变语义。

## 11. G9：资源使用有界且任务可取消

### 目标

大轨迹不能要求整体载入内存，pair 矩阵不能无界增长，GUI 不能在主线程计算。取消应在
合理时间内生效，并且与失败一样不发布半成品。

### 当前机制

- 轨迹按帧迭代；
- pair distances 按 `max_pairs_per_chunk` 分块；
- 文件 hash 以 4 MiB 块读取；
- XDR 帧偏移 cache 按源文件元数据失效，使用文件锁和原子替换，不在 trajectory 旁生成
  sidecar；
- `JobRunner` 默认单工作线程；
- 帧边界、hash chunk 和外部进程轮询都有取消检查；pair chunk 内当前没有独立取消点；
- GUI 用 `QTimer` 轮询 job handle 状态，不从工作线程直接操作控件。

### 验收标准

- 配置上限决定峰值 pair 内存，原子对总数不改变该上限；
- 删除或失效的 XDR 帧偏移只触发重扫，不改变分析结果；
- 取消后 job 状态明确，不写结果、不提交项目；
- 进度单调且能区分运行、成功、失败、取消；
- 外部进程取消时先 terminate、等待后再 kill；超时时直接 kill；
- 新的长循环必须增加取消点和进度测试。

## 12. G10：完整 Backend 行为确定

### 目标

相同请求的 Backend 选择必须可预测。一个已注册 adapter 负责所支持分析的 reader、selection、
frame handling 与 computation，并必须进入 provenance。同一次尝试禁止混合不同 Backend 的组件。

### 当前机制

- `native` 固定使用 Native GRO reader、NDX selection 和 Native 径向算法；
- `mdanalysis` 固定使用 MDAnalysis reader、selection、frame handling、distance 与 Energy；
- `gromacs` 默认把原输入直接传给 `gmx rdf`，仅 cumulative RDF 添加 `-cn`；非默认范围先用 `gmx check` 获取帧数，再用一次 `gmx trjconv -fr`，并使用 GROMACS selection 与 `gmx energy`；
- `auto` 按 adapter 声明的优先级选择完整策略；source 加载失败时可尝试下一条完整策略；
- 显式 Backend 不 fallback；一次尝试内不混用；
- 所有 Backend 都输出统一的 nm、ps 与结果契约。

### 验收标准

- requested/resolved Backend 决策有单元测试并进入 provenance；
- native 明确拒绝不支持的输入；
- 多帧 GRO 的原子数和身份变化会失败；
- MDAnalysis 的埃到 nm 转换和三斜盒转换有测试；
- 同一可表达体系在不同后端的分析结果满足明确数值容差。

## 13. G11：多表现层语义等价且职责清晰

### 目标

CLI、TUI 和 GUI 可以有适合媒介的交互，但不能拥有不同的分析默认、选择语义或项目格式。

### 当前机制

- CLI 将最终 JSON 写 stdout，进度/诊断写 stderr；
- TUI 用会话状态和各分析独立 draft 构造 request；
- GUI 用 session 保存输入/草稿，以后台 job 调用相同门面；
- 三者的结果展示和导出都来自 `AnalysisResult`/`PlotModel`；
- Qt 在 GUI 包内惰性导入，Linux headless 路径不依赖 Qt。

### 验收标准

- 同一配置跨入口形成等价 request；
- 前端测试同时验证 request 和控件行为；
- CLI stdout 可直接被 JSON 消费者解析；
- TUI 的不同分析草稿不会串扰；
- GUI 主线程保持响应，错误回到主线程呈现；
- 界面使用平面化设计，不依赖小字号说明来弥补信息架构。

## 14. G12：绘图与数据分离

### 目标

绘图提供结果的可重复视图，结果数据只保存在结果契约中。标题、配色、可见性和坐标
范围可以改变，但不能改写结果数组。

### 当前机制

- `core/plotting.py` 构造工具包无关的绘图模型；
- RDF 和 CN 按 radial domain 分组，可共享横轴并使用双纵轴；
- 当前配色方案为 `Residue name` 与 `Fixed color`；
- 当前所选绘图的自定义标题会进入绘图状态并用于项目恢复和图片导出；
- 选择配色或范围后直接应用，不需要 Auto/Apply 按钮；
- PNG 以 300 dpi 输出，SVG/PDF 为矢量输出。

### 验收标准

- `Residue name` 由结果诊断中的目标/配体残基名形成稳定颜色键；
- 缺少或多个残基名时有确定性去重、排序和组合规则；
- `Atom name` 不作为当前配色方案；
- 自动范围只基于当前可见序列及有效数值；
- 导出图和 GUI 图消费同一绘图模型；
- 合并绘图中的序列使用同一个自定义标题；
- 绘图状态变化不改变项目中的分析结果。

## 15. G13：外部程序被隔离并可审计

### 目标

外部可执行程序是不可完全信任的系统边界。发现、检测和运行必须不用 shell，并保留足够
记录用于诊断。

### 当前机制

- `integrations/manager.py` 负责候选顺序与状态管理；
- `integrations/gromacs.py` 描述 GROMACS 身份和能力；
- `runtime/detection.py` 与 `runtime/execution.py` 提供通用安全检测和执行；
- 使用显式 argv、cwd、受控环境、超时和输出捕获；
- 运行记录包含身份、版本、退出码、耗时和输出 hash。

### 验收标准

- 不通过 shell 拼接用户输入；
- 可执行路径和 argv 保持独立；
- 超时、取消、启动失败和非零退出可区分；
- 外部工具只有在明确选择 GROMACS，或 Auto 选中完整 GROMACS 流水线时才能产生结果数据；
  实际 Backend 必须记录；
- 新工具复用 runtime，不复制子进程管理代码。

## 16. G14：配置和模板可验证、可迁移环境

### 目标

用户偏好可以在免安装目录中确定地定位，损坏配置必须给出明确错误。模板只减少
重复输入，不引入隐藏行为。

### 当前机制

- 配置使用严格 TOML schema 1；
- 显式 `MDHELPER_CONFIG` 优先，否则使用可执行程序同目录的 `config.toml`；
- 保存后重新读取校验再原子替换；
- 内置模板是包资源，用户模板独立保存；
- 打包配置显式包含模板、schemas、方法和验证文档。

### 验收标准

- 未知配置字段和错误类型失败；
- 配置命令可以在其他配置无效时用于检查/修复；
- wheel 和冻结程序中资源发现不依赖源码工作目录；
- portable 模式不覆盖用户显式环境变量；
- 模板展开产生普通 request，且内容经过相同校验。

## 17. G15：错误可行动、日志不成为契约

### 目标

错误应说明失败类别和用户可采取的动作，同时保留底层上下文供开发者定位。表现层不得靠
解析任意英文异常文本决定业务流程。

### 当前机制

- core 定义领域错误类别；
- app 在用例边界添加上下文；
- CLI 映射为结构化输出和退出状态；
- TUI/GUI 映射为当前工作流中的可恢复提示；
- runtime logging 写平台用户日志路径，失败时不阻止程序启动。

### 验收标准

- 输入错误、方法限制、取消、外部工具失败和内部错误可以区分；
- GUI 不从工作线程弹对话框；
- 日志不得包含程序继续运行所必需的唯一数据；
- 日志初始化失败安全降级；
- 错误消息无需小字号脚注才能理解下一步操作。

## 18. G16：扩展成本受控

### 目标

新增分析、轨迹后端、外部工具或表现层时，变更集中在对应扩展点，不需要复制整个调用链。

### 当前机制

- 分析使用 registry；
- 轨迹使用 `TrajectorySource`；
- 选择使用统一服务和引擎协议；
- 外部工具拆分 integrations 与 runtime；
- 前端统一经 `ApplicationService`；
- schema、方法、验证和 package data 明确列出跨切面工作。

### 验收标准

- 新分析有契约、实现、注册、方法、验证、导出和前端入口；
- 新后端不静默修改既有方法公式；
- 新表现层不导入已有表现层；
- 新资源进入安装包和冻结包；
- 新代码通用，不针对测试名、文件名、类名、样例名或特定软件文本写特判。

## 19. 当前关键设计决策

| 主题 | 当前决定 | 原因 |
| --- | --- | --- |
| 统一入口 | 无参数优先 GUI、不可用时降级 TUI；显式模式选择 GUI/TUI/CLI | 单一产物不混合表现层实现。 |
| 桌面入口 | Windows GUI，Linux 可选 GUI | Windows 默认提供，Linux wheel 不强制 Qt。 |
| 产物大小 | 每个发布产物不超过 256 MB | 防止重复 runtime 和无用依赖回归。 |
| 分析 Backend | Native、MDAnalysis、GROMACS 三条完整流水线 | reader、selection、frame/computation 不混用，选择可测试、可复现并完整记录。 |
| Auto 语义 | 按 adapter 优先级选择可用完整策略 | source 加载失败可尝试下一条完整策略，显式选择不 fallback。 |
| 选择 | Native 仅 NDX；MDAnalysis 使用 NDX 或静态 MDAnalysis 表达式；GROMACS 使用 NDX 或 GROMACS expression | 语法所有权明确，结果在运行中固定、可记录。 |
| 分析参数 | 请求显式给出 | 避免不可审计的参数推断。 |
| 角色识别 | 基于电荷/数量的建议并需确认 | 不把命名习惯误当化学事实。 |
| 第一壳层 | 运行后诊断 | 不影响原始曲线和请求参数。 |
| 项目格式 | JSON manifest + 独立结果 + hash | 可读、可恢复、可校验。 |
| 并发 | 默认单分析工作线程 | GUI 响应且资源使用有界。 |
| 绘图配色 | Residue name / Fixed color | 聚合序列有稳定、明确的颜色键。 |
| 不确定度 | 当前未实现 | 不在无验证方法时提供伪精度。 |
| GROMACS | 可选完整 Backend | RDF 使用 `gmx rdf -o`，cumulative RDF 添加 `-cn`，抽样范围可用 `gmx trjconv -fr`，Energy 使用 `gmx energy`，命令完整审计。 |
| 缓存 | 仅缓存可重建工作数据 | 项目中的 XDR 帧偏移和 GROMACS 工作文件统一使用项目 `cache/`；不缓存规范分析结果。 |

## 20. 非目标与已知限制

以下内容不属于当前已实现目标：

- 完整替代 GROMACS、MDAnalysis、VMD 或其他通用 MD 生态；
- 动态逐帧选择；
- 自动 `r_max`/bin/cutoff 参数推荐；
- 基于原子名的绘图配色方案；
- bootstrap、块平均、误差条或置信区间；
- 分析结果缓存及失效策略；XDR 帧偏移 cache 已实现；
- 第三方分析插件的安装、发现和沙箱；
- 网络服务、远程任务调度或多用户项目锁；
- 所有轨迹格式的原生解析；
- 仅凭单个测试体系宣称广泛方法有效性。

具体格式限制、验证空白和平台限制以 `docs/KNOWN_LIMITATIONS.md` 为准。发现新限制时应先
记录，再决定是修复、拒绝输入还是扩大验证范围，不能以静默 fallback 掩盖。

## 21. 发布质量门

### 21.1 方法质量门

- RDF、CN 方法文档与代码一致；
- 已发布分析有独立可解释的期望值和容差；
- PBC、变盒、选择重叠、帧范围和空选择均被覆盖；
- 结果契约包含单位、方法和 provenance；
- 尚未验证的范围明确列入限制。

### 21.2 软件质量门

- 全部单元、集成和架构测试通过；
- Ruff、mypy 和源码 ASCII 检查通过；
- 请求/结果/project schema 与运行时校验同步；
- 原子写入、取消和项目损坏路径有测试；
- 无针对测试或样例的特殊分支。

### 21.3 平台与发行门

- Linux 在没有 Qt 的环境可运行 TUI、CLI 和全部非 GUI 测试；
- Linux x86_64 独立归档无需安装 Python 或 Qt 即可启动 TUI 和 CLI；
- Windows 和 Linux 都只发布经过目标平台 smoke test 的便携归档；
- Windows CLI/TUI 与 Linux 使用相同应用和分析层；
- Windows GUI 的关键加载、配置、运行、取消、结果和绘图流程通过测试；
- wheel 包含模板、schemas、方法、验证和用户文档；
- 冻结 smoke test 必须实际启动入口和读取资源，不能只检查文件存在；
- 便携配置和普通用户配置互不意外覆盖。

## 22. 变更评审清单

每个影响行为的变更都应回答：

1. 它修改了哪个领域契约或用例？
2. 公式、单位、PBC 或帧采样是否变化？
3. 三个表现层是否仍构造相同语义的请求？
4. 是否新增隐式默认、推荐或 fallback？其证据能否进入 provenance？
5. 运行时 Python 校验和发布 JSON Schema 是否同步？
6. 大输入下的内存、时间、进度和取消是否仍有界？
7. 失败时是否可能留下半写文件或未校验项目状态？
8. 新依赖是否停留在正确外层，Linux headless 是否仍可用？
9. 新资源是否进入 wheel 和冻结包？
10. 方法、验证、限制和用户文档是否与实现同步？

只有代码、测试、契约和文档共同闭环，功能才算完成。MDHelper 的核心质量标准要求相同输入
和显式决策稳定地产生可解释、可审计、可恢复的分析结果。
