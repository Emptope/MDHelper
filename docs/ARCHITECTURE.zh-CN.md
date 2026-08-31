# MDHelper 0.1.0 软件架构

[English](ARCHITECTURE.md) | [简体中文](ARCHITECTURE.zh-CN.md)

本文描述仓库当前实现，而不是未来路线图。它面向需要修改、评审、测试或发布
MDHelper 的软件工程师。算法的集中说明见 `docs/ALGORITHM.md`，方法的发布定义见
`docs/methods/`，验证证据见 `docs/validation/`，已知限制见
`docs/KNOWN_LIMITATIONS.md`。

## 1. 系统边界

MDHelper 是一个 Python 3.12 分子动力学分析应用。0.1.0 提供径向分布函数（RDF）、
累积配位数（CN）和 EDR energy 提取。程序可以读取纯 Python 原生后端
支持的 GRO 轨迹，也可以通过 MDAnalysis 读取更广泛的拓扑、轨迹组合和 EDR 文件。选择
来源可以是 GROMACS NDX 组或静态 MDAnalysis 选择表达式。

系统有三个表现层：

- TUI 是引导式终端交互入口，也是 GUI 不可用时的降级入口；
- CLI 是稳定的无交互自动化入口；
- GUI 是 Qt 和 display 可用时无参数启动的优先入口。

三个表现层共享同一个应用服务和数据契约，不复制分析算法。GROMACS 是可选外部工具；显式
`gromacs` request 可作为原生 RDF、CN、trajectory 或 Energy 后端。

## 2. 架构原则与依赖方向

```text
CLI / TUI / GUI
        |
        v
ApplicationService facade
        |
        v
app use cases -----------------------> workflow
        |                                  |
        +--> analysis --> plugins          |
        +--> services --> backends         |
        +--> project                       |
        +--> io                            |
        +--> integrations --> runtime      |
        |                                  |
        +----------------------------------+
                         |
                         v
                        core
```

箭头表示“可以依赖”。`core` 是最内层：只能依赖标准库、第三方基础库和
`mdhelper.core` 自身，不能反向导入其他内部包。CLI、TUI、GUI 不能彼此导入，也不能
直接导入 `analysis` 或 `backends`。这些约束由 `tests/test_architecture.py` 静态检查。

- `core` 定义稳定的数据形状、协议和错误语义，不负责装配或 I/O；
- `backends` 把具体轨迹库适配成 `core` 协议；
- `analysis` 只实现分析计算；
- `services` 组合后端和基础设施，提供系统、选择、配置和 provenance 等能力；
- `app` 编排一次用户用例，是所有表现层进入业务系统的边界；
- `project` 负责可恢复、可校验的磁盘状态；
- `workflow` 负责后台任务生命周期，不改变分析语义。

## 3. 包布局

```text
src/mdhelper/
  bootstrap/       启动和便携模式
  core/            领域数据、协议、错误和绘图模型
  app/             应用用例与统一门面
  analysis/        RDF、CN、溶剂化和 energy 分析算法
  plugins/         分析函数注册表
  services/        配置、系统、选择、provenance 和模板服务
  backends/        GRO、MDAnalysis 和 GROMACS 轨迹及选择适配器
  io/              NDX 读取与结果/图像导出
  project/         项目清单、结果仓库和原子存储
  workflow/        同步/异步任务执行
  integrations/    外部程序的领域适配
  runtime/         子进程、检测、环境和日志基础设施
  cli/             无交互命令行表现层
  tui/             编号菜单终端表现层
  gui/             Qt 桌面表现层
  resources/       内置模板等只读资源
```

包根目录只保留 `__init__.py`、`__main__.py` 和 `version.py`。业务实现不得重新堆回根
目录；该规则同样由架构测试保护。

## 4. 启动与组合根

| 文件 | 职责 |
| --- | --- |
| `mdhelper/__init__.py` | 暴露版本等最小公共信息，不执行重量级初始化。 |
| `mdhelper/__main__.py` | 支持 `python -m mdhelper`，转入统一终端启动器。 |
| `mdhelper/version.py` | 定义单一应用版本 `0.1.0`。 |
| `bootstrap/portable.py` | 处理便携配置位置和统一界面分派。 |

无参数调用优先进入 GUI，不可用时降级到 TUI；显式 `gui`、`tui`、`cli` 模式仍保持表现层
分离，其他参数进入 CLI。Windows 只构建一个控制台子系统启动器，使 PowerShell 等终端在
TUI/CLI 运行期间保持等待并连接标准流。GUI 启动会创建独立的无控制台应用进程，随后结束外层
启动进程，使临时 Windows Terminal 窗口在 Qt 主窗口继续运行前关闭。终端模式保留继承的
控制台，必要时自行创建。所有冻结程序都把配置定位到可执行文件旁；显式
`MDHELPER_CONFIG` 仍优先。便携逻辑只决定位置，不绕过配置校验。

真正的组合根是 `app/facade.py` 中的 `ApplicationService`。它创建应用上下文和用例
对象，并向三个表现层提供统一接口。轨迹加载器、分析注册表和 Integration 注册表可以注入，
使测试无需依赖真实 GUI、真实外部程序或特定轨迹库。

## 5. `core`：稳定领域内核

`core` 不表示“算法后端”。它是内外层共享的类型和协议集合，负责规定数据是什么、
错误如何表达、边界如何校验。

| 文件 | 工作原理与关系 |
| --- | --- |
| `analysis.py` | 定义 `AnalysisRequest`、`AnalysisResult` 及 JSON 转换。请求包含分析类型、输入、选择、显式参数、帧范围、轨迹后端、物种角色和参数决策记录；结果包含方法、数值、诊断和 provenance。契约 schema 版本当前为 1。 |
| `system.py` | 定义 `Atom`、`Box`、`Frame`、`FrameRange`、`SystemSummary`。`Frame` 是算法逐帧消费的最小对象；`Atom.molecule_id` 是按残基/分子计数的稳定键。当前没有 `MDSystem`、`Molecule` 或 `Species` 实体类。 |
| `trajectory.py` | 定义 `TrajectorySource` 协议。分析层只要求原子元数据、帧数和帧迭代，不知道 GRO 或 MDAnalysis。 |
| `selection.py` | 定义选择引擎协议，使 NDX 和 MDAnalysis 选择最终都转换为零基原子索引。 |
| `species.py` | 定义阳离子、阴离子、溶剂等角色词汇和建议对象。角色是解释性元数据，不能改变选择集合、截断半径或数值算法。 |
| `plotting.py` | 定义与 Qt/窗口无关的 `PlotSeries`、`PlotModel`、配色、坐标范围、选择和状态对象，负责结果分组及绘图状态规范化。 |
| `errors.py` | 定义可归类的领域错误。外层据此选择退出码、对话框或日志，而不是匹配任意异常文本。 |
| `progress.py` | 定义进度回调和取消检查所需的契约。 |
| `templates.py` | 定义分析模板的领域表示。 |
| `units.py` | 集中声明内部和展示单位约定。 |
| `__init__.py` | 统一导出核心公共类型，不放业务逻辑。 |

### 5.1 请求和结果契约

`AnalysisRequest` 是执行的唯一事实来源。GUI 控件、TUI 草稿和 CLI 参数必须先转换为
这个对象，算法不能再从界面状态读取隐含参数。帧范围采用 Python 切片语义：`start` 包含、
`stop` 不包含，并按 `stride` 取样；
`r_max` 与 bin width 均由用户或模板显式给出。

`AnalysisResult` 是表现层和导出的共同输入。数组存放在结构化 `data` 中，解释信息放在
`diagnostics`，复现信息放在 `provenance`。请求与结果都经过严格解析：必填字段缺失、
未知字段、非法枚举和不一致数组会在边界处失败。

`AnalysisRequest.from_dict()` 和 `PlotState.from_dict()` 只接受 0.1.0 当前字段。未知字段、
缺失字段、旧分析标识和旧绘图状态均直接失败；最初开发版本不包含数据迁移分支。

内部距离单位为 nm，时间单位为 ps。径向绘图可以显示为埃，但转换只发生在展示模型，
不会改写持久化结果数据。

### 5.2 绘图领域模型

`core/plotting.py` 将“分析结果如何组成一张图”从 GUI 中抽出：

- RDF 与 CN 的横轴都是径向距离，可组合到同一绘图域；
- 两种量同时存在时使用共享横轴和双纵轴；
- energy term 默认各自形成独立绘图窗口，每个窗口仅有一张图，可通过显式 group 合并到
  同一窗口的共享坐标轴；
- `Residue name` 配色由序列的目标/配体残基名产生稳定键；
- `Fixed color` 以序列标识保存显式颜色；
- 同一选择的次坐标轴序列使用更暗颜色和虚线，保持关联但可辨认；
- 自动横轴取可见序列定义域的交集，自动纵轴根据当前横轴范围内的数据计算；
- GUI 改变配色或范围后直接更新状态，不存在额外的 Auto/Apply 提交阶段。

绘图状态逐行保存 result ID、result series、panel group、可见性、legend、颜色和自定义
标题，因此同一 energy result 的多个 term 可以独立恢复、组合和导出。GUI 编辑当前可见
序列所属绘图的标题，并同步到该绘图的其他分组序列；项目恢复和图片导出使用同一状态。

当前绘图配色不支持 `Atom name`。原子名可以用于选择表达式和选择诊断，但一条聚合分析
序列往往包含多个原子名，不能形成无歧义的一对一颜色键。

## 6. `app`：用例编排与统一门面

表现层只能调用这一层完成业务动作。它负责“按什么顺序调用哪些能力”，但不实现 RDF
公式或具体文件解析。

| 文件 | 工作原理与关系 |
| --- | --- |
| `context.py` | 保存配置文件、已校验配置、轨迹加载器、分析注册表和 Integration 管理器，依赖均可替换。 |
| `facade.py` | 构造 `ApplicationService`，聚合 analyses、checks、projects、integrations、templates 等用例，形成前端唯一业务入口。 |
| `analyses.py` | 校验请求，解析可用后端，加载轨迹，检查角色，生成输入指纹，调用分析注册表并校验结果。具体分析函数通过选择服务或所选外部后端处理选择；导出由同一用例对象的独立方法完成。 |
| `checks.py` | 读取系统摘要、选择组大小和角色建议，供前端在真正运行前检查输入。 |
| `projects.py` | 包装项目输入发现、创建、打开、结果查询和提交，不向表现层泄露仓库细节。New Project 非递归发现所选目录直属的 `.tpr`/`.gro` topology、`.xtc`/`.trr`/`.gro` trajectory 和可选 `.ndx`，进行大小写不敏感匹配并稳定排序。 |
| `integrations.py` | 检测、查询和运行外部软件，并返回结构化状态与运行记录。 |
| `templates.py` | 列出、读取和保存分析模板。 |
| `reports/` | 定义 GUI 与 TUI 共用的 `Report` 基类；RDF、CN、energy 子类分别负责各自结果与配置字段，表现层只负责 HTML 或终端渲染。 |
| `__init__.py` | 导出应用层公共接口。 |

```text
presentation
  -> ApplicationService
  -> AnalysisUseCases.run(request)
  -> trajectory loader
  -> provenance service
  -> AnalysisRegistry.get(analysis_type)
  -> analysis runner -> selection service
  -> AnalysisResult validation
  -> caller-requested export/project commit
  -> presentation
```

应用层会记录角色信息，但角色不完整只产生诊断警告；它不会替换用户选择，也不根据数据
自动改变 `r_max`。第一配位壳位置是运行后的诊断，不是运行前参数推荐器。

## 7. `plugins` 与 `analysis`：分析计算

### 7.1 分析注册表

`plugins/analysis.py` 提供窄接口注册表：分析名映射到可调用分析函数。
`analysis/__init__.py` 注册 RDF、CN 和 energy 内置实现。这里的“插件”当前仅是
进程内函数注册机制，不包含第三方包发现、动态安装、权限隔离或独立进程协议。

新增分析应先定义请求/结果形状，再实现与注册函数，最后由应用层和表现层暴露；不应在
CLI 或 GUI 中直接调用算法文件。

### 7.2 通用数值基础

`analysis/common.py` 统一帧审计、进度/取消、每帧可靠半径检查、三斜盒最小镜像和
有界 pair 分块。RDF 和 CN 都依赖这些不变量，
不能在各自文件中复制一套 PBC 或帧逻辑。

### 7.3 RDF 与 CN 共享算法

`analysis/radial.py` 是 RDF 和 CN 的共享数值实现：一次累积半宽 pair histogram，再分别
重采样到中心对齐 RDF grid 和边界对齐 cumulative grid。`rdf.py`、`cumulative_rdf.py` 只把
共享 profile 组装成各自的结果契约和诊断。
第一壳层是结果后的独立诊断，不修改原始曲线。

`analysis/gmx_rdf.py` 是显式 GROMACS RDF/CN runner。它保留零基 Python 帧切片语义，通过
Integrations 调用带 `-cn` 的 `gmx rdf`，把两条 XVG 曲线解析到统一结果契约，并记录
trajectory conversion 与 RDF 命令。全帧和连续帧可直读原轨迹；stride 范围使用精确转换
子集。

PBC、分块、网格、归一化、累计公式、端点和第一壳层峰谷规则集中记录在
`docs/ALGORITHM.md`；发布定义和验证容差分别见
`docs/methods/rdf-1.0.0.md`、`docs/methods/cumulative-rdf-1.0.0.md` 与对应验证文档。

| 文件 | 职责 |
| --- | --- |
| `rdf.py` | 调用共享径向计算，发布半径、`g(r)` 和第一壳层诊断。 |
| `cumulative_rdf.py` | 调用同一径向计算，发布 `cumulative_rdf` 的 `N(r)`；若识别到第一壳层最小值，同时报告该半径处配位数。 |
| `energy.py` | GROMACS 后端通过 Integration 发现 EDR term 并调用 `gmx energy`；MDAnalysis 后端通过 `EDRReader` 直接读取 term、时间、数值和单位；两者共用结果契约和 App 发现用例。 |
| `gmx_rdf.py` | 通过 Integration 调用 `gmx rdf`/`-cn`，解析 RDF/CN XVG 并记录原生命令 provenance。 |
| `radial.py` | RDF/CN 共用直方图、RDF 归一化、CN 累计和壳层诊断。 |
| `common.py` | PBC、分块距离、帧审计、进度、取消和共享计数。 |

当前分析结果是对明确帧集合的确定性统计，没有 bootstrap、块平均置信区间或其他不确定
度估计。诊断曲线平滑也不是结果数据的不确定度。

## 8. `services`：基础业务服务

### 8.1 系统与物种角色

`services/system.py` 通过轨迹源构造 `SystemSummary`，包括原子、残基、元素、可用电荷和
帧信息。角色建议使用通用的分子净电荷和种群证据；模糊情况标记为不可用并要求用户确认。
精确阈值、分支和置信度规则见 `docs/ALGORITHM.md`。

实现不按 `SOL`、`Li` 等具体名称写特判。角色只是 provenance 和解释信息，不能影响
选择结果或分析数值。完整规则见 `docs/SPECIES.md`。

### 8.2 选择服务

进程内分析由 `services/selection.py` 统一两种选择源：请求给出 index file 时，使用
`io/ndx.py` 的命名组；否则使用 `backends/mdanalysis_selection.py` 解析静态选择表达式。
GROMACS RDF/CN 有 index 时引用精确 NDX 组名，没有 index 时把 GROMACS selection
expression 传给 `gmx rdf`。

服务返回稳定、零基、去重的原子索引，并记录组名或表达式、索引文件哈希、选中原子名、
残基名和解析器来源。分析开始后选择固定，不随帧动态变化。动态选择关键词会被明确拒绝，
避免不同后端产生不同语义。选择语法见 `docs/SELECTIONS.md`。

### 8.3 配置、provenance、工具和模板

`services/config.py` 读取和保存 TOML schema 1。配置覆盖 GUI 主题/字体、分析 pair chunk
上限和外部工具路径。路径解析优先使用显式 `MDHELPER_CONFIG`，否则使用可执行程序同目录配置。
解析拒绝未知字段和非法类型；保存采用同目录临时文件、重新读取校验和
原子替换。详见 `config.example.toml` 与 `docs/CONFIGURATION.md`。

`services/provenance.py` 以 4 MiB 块计算 SHA-256，并在块边界检查取消状态。provenance
包括应用/Python/关键依赖版本、平台、实际 reader、输入路径和哈希、角色及参数决策。
选择解析和帧审计由分析函数在结果 `diagnostics` 中记录。

`integrations/manager.py` 按本次覆盖、配置路径、配置搜索路径、环境、`PATH` 和 adapter
候选路径的顺序检测外部软件。`services/templates.py` 递归发现非隐藏 ASCII 模板，并原子
保存用户模板。

| 文件 | 主要职责 |
| --- | --- |
| `system.py` | 加载系统摘要和通用角色建议。 |
| `selection.py` | 将不同选择源解析为统一索引及诊断。 |
| `config.py` | 配置路径、严格 TOML 校验和原子保存。 |
| `provenance.py` | 输入哈希和运行环境记录。 |
| `templates.py` | 内置/用户模板发现、读取和保存。 |

## 9. `backends`：轨迹与选择适配

### 9.1 轨迹分派

`backends/trajectory.py` 根据 reader 模式分派：

| 模式 | 行为 |
| --- | --- |
| `native` | 强制使用 `GroTrajectorySource`；输入不受支持或解析失败就报错。 |
| `mdanalysis` | 强制使用 `MDAnalysisTrajectorySource`。 |
| `gromacs` | 通过 Integrations 调用本机 `gmx trjconv`，再读取标准化的多帧 GRO。 |
| `auto` | topology 和 trajectory 都是 GRO 时选择原生后端，否则选择 MDAnalysis。 |

`auto` 是确定性选择规则，不是失败后的级联重试。这样可避免同一输入因某后端偶发失败而
静默切换实现，损害可复现性。

### 9.2 后端文件

`backends/gro.py` 以流式方式读取单帧或多帧 GRO：使用固定列解析残基号、残基名、原子
名、原子号和 nm 坐标；从标题读取可用时间；支持 3 个正交盒参数和 9 个三斜盒参数；
第一帧建立原子元数据，后续帧验证原子数量和身份不变；不虚构 GRO 中不存在的电荷。

`backends/mdanalysis.py` 构造 `MDAnalysis.Universe`，把帧适配为 core `Frame`：坐标从埃
转换为 nm，盒长/角转换成盒矩阵，时间统一为 ps。原子元数据在可用时包含元素和电荷；
`segid:resname:resid` 组合成分子标识，供按分子计数。

XTC/TRR reader 通过通用 XDR reader 子类把 MDAnalysis 的 `*_offsets.npz` 和 lock 文件定向
到应用提供的 cache 目录。非 XDR reader 不创建这类缓存；不得在分析完成后才移动 sidecar，
因为那会导致下一次加载重新扫描并再次污染输入目录。

`backends/gromacs.py` 只负责转换结果的缓存和标准轨迹端口；可执行文件检测、能力校验与
`gmx trjconv` 执行均由 Integrations 完成，上层分析不接触可执行程序路径。
显式 GROMACS RDF/CN 不用该转换端口生成曲线，而是把原输入路径直接传给 `gmx rdf`；
内置 reader 只提供 metadata 和帧边界。

`backends/mdanalysis_selection.py` 从 core 原子元数据构造轻量 Universe 解析静态表达式，
避免应用层依赖 MDAnalysis 对象。`backends/common.py` 提供输入存在性检查和基于原子名的
通用元素推断；推断规则不能针对测试样例或具体体系。

## 10. `io`：边界格式

`io/ndx.py` 严格读取 UTF-8（允许 BOM）的 GROMACS NDX 文件。组名精确匹配，文件中的
一基索引转换为内部零基索引。重复组、非法整数、重复原子、非正索引、越界索引或空组
都会产生明确错误，不做静默修复。

`io/export.py` 支持 JSON、CSV、PNG、SVG 和 PDF：JSON 保留完整结果契约；CSV 使用
稳定列和 15 位有效数字；Matplotlib 使用非交互 Agg 后端，PNG 默认 300 dpi；SVG/PDF
保留矢量输出。所有写入先在目标目录生成临时文件，成功后原子替换。导出以
`AnalysisResult` 或 `PlotModel` 为输入，因此三个表现层的数据语义相同。

## 11. `project`：项目聚合与持久化

```text
project-root/
  mdhelper-project.json
  results/
    data/
  figures/
  cache/
```

`cache/` 保存 MDAnalysis XDR reader 的帧偏移索引等可重建性能数据，不保存分析结果。
偏移索引按轨迹路径生成稳定名称，以轨迹大小、纳秒修改时间和原子数校验失效，并使用文件锁
和原子替换写入。项目分析和检查显式传入项目 cache；尚未绑定项目的轨迹使用轨迹同目录下的
`cache/`。任何 cache 文件都可以删除，之后只会重新构建而不会改变分析语义。

| 文件 | 工作原理与关系 |
| --- | --- |
| `project.py` | `Project` 聚合 manifest、input 和 result 仓库，向应用层提供创建、打开、提交和读取。 |
| `manifests.py` | 严格校验 `mdhelper-project.json`；记录输入、结果索引和 schema 版本，不迁移旧字段。 |
| `inputs.py` | 优先解析项目相对输入路径，再尝试原绝对路径；移动后的文件只有 SHA-256 相同才重新关联。 |
| `results.py` | 验证请求/结果/provenance，写入结果，计算哈希并更新 manifest；读取时检查路径、哈希和契约。 |
| `schema.py` | 运行时 Python schema 校验器，递归拒绝未知字段、缺失字段和错误类型。 |
| `storage.py` | JSON 序列化、同目录临时文件和 `os.replace` 原子替换等底层存储原语。 |
| `__init__.py` | 导出项目公共接口。 |

结果提交顺序是：严格校验请求、结果和输入 provenance；将一份完整结果原子写入
`results/data/`；计算文件哈希；将路径和哈希加入 manifest 并原子提交。若 manifest
提交失败，刚创建且未被索引的文件会被删除。

读取时拒绝结果路径逃逸 `results/data/`；每条记录必须带结果哈希，加载时会校验该哈希，
随后重新解析结果契约。
`schemas/` 中的 JSON Schema 面向发布、测试和外部工具；运行时以 `project/schema.py`
的严格校验为准，二者变更必须同步。

## 12. `workflow`：任务状态与取消

`workflow/tasks.py` 提供 `TaskService` 和 `TaskHandle`。默认使用单工作线程的
`ThreadPoolExecutor`，保证 GUI 不阻塞且同一会话不会无界并发占用内存。

handle 保存待运行、运行中、成功、失败或取消状态，以及进度、结果、结构化错误、取消
事件和 future。GUI 提交后台任务后用 `QTimer` 轮询 handle 状态；CLI 和 TUI 调用同步包装，但
仍使用同一任务语义。

取消是协作式的：分析帧边界、文件哈希块和子进程轮询点检查取消事件；pair chunk 内当前
没有独立取消点。取消后不得提交不完整结果或项目记录。

## 13. 表现层

### 13.1 CLI

| 文件 | 职责 |
| --- | --- |
| `parser.py` | 声明命令、参数、类型和帮助文本，不执行业务。 |
| `main.py` | 建立配置和 `ApplicationService`，分派命令并转换领域错误。 |
| `commands.py` | 通用命令处理和共享分派。 |
| `analysis_commands.py` | 将 RDF、CN、energy 参数转换为 `AnalysisRequest`。 |
| `config_commands.py` | 配置查看和修改。 |
| `project_commands.py` | 项目创建、打开和结果操作。 |
| `integration_commands.py` | 外部软件列出、检测和执行。 |
| `output.py` | 保证 stdout 只含最终机器可读 JSON，进度和诊断写 stderr。 |
| `__main__.py` | 支持 `python -m mdhelper.cli`。 |

CLI 适合脚本和 CI。SIGINT 转换为取消请求。配置命令在完整应用构造前处理，避免损坏配置
阻止用户执行修复命令。

### 13.2 TUI

| 文件 | 职责 |
| --- | --- |
| `terminal.py` | 抽象输入、输出和终端能力，便于非交互测试。 |
| `model.py` | 保存 workspace、各分析独立草稿和当前菜单状态。 |
| `controller.py` | 实现编号菜单状态机、返回规则、运行前审核和服务调用。 |
| `formatting.py` | 渲染共享结果报告，并格式化 TUI 错误和选择摘要。 |
| `main.py` | 创建终端、应用服务和控制器。 |
| `__main__.py` | 支持 `python -m mdhelper.tui`。 |

Workspace 保存当前输入和检测结果；各分析草稿相互独立，避免参数串扰。运行前审核面板
集中展示输入、选择、帧范围和分析参数。检测到的物种角色须经用户确认才参与已配置运行，
但确认不会改变分析选择。RDF + CN 工作流从同一套径向配置构造两个 request，分别导出原始
结果，并把共享距离轴和双 Y 轴的合并图委托给公共绘图用例。workspace 未加载时状态机显示
明确的 project/workspace 状态和 Load 菜单，成功加载输入或项目后才显示精简主菜单；Tools
中的 Integrations 与 Templates 保持为独立状态。选定 EDR 后通过 App 用例按所选 Backend
发现 terms；`auto` 先使用 MDAnalysis，无法读取时才按已检测 capability 回退到
`gmx energy`，随后以带选中标记的有序多选菜单编辑 terms。

### 13.3 GUI

GUI 采用薄视图加会话控制器分工，Qt 只在 GUI 包内惰性导入，Linux CLI/TUI 测试不需
安装或初始化 Qt。

| 文件 | 职责 |
| --- | --- |
| `main.py` | GUI 入口、Qt 应用创建和顶层异常边界。 |
| `window.py` | 主窗口编排器，连接 load、analysis、task、result 和 menu 子模块。 |
| `session.py` | 保存当前输入、系统摘要、项目、分析草稿和展示状态。 |
| `load.py` | 轨迹/拓扑/index 加载流程和加载后状态更新。 |
| `inputs.py` | 输入控件构造、路径读取和启用状态。 |
| `species.py` | 角色建议、确认和用户选择界面。 |
| `analysis.py` | 分析类型切换、请求构造和运行编排。 |
| `parameters.py` | `r_max`、bin width、cutoff 和帧采样等显式参数控件。 |
| `selections.py` | 参考、目标、配体选择及批量 plot series 编辑。 |
| `tasks.py` | 将后台 `TaskHandle` 映射为进度条、取消按钮和完成回调。 |
| `results.py` | 结果页、表格/摘要和项目结果加载。 |
| `plot_window.py` | 渲染 core 绘图模型；配色和坐标选择后立即应用。 |
| `formatting.py` | 把共享结果报告渲染为 GUI HTML，并格式化 GUI 错误和选择摘要。 |
| `dialogs.py` | 统一错误、确认和文件对话框。 |
| `projects.py` | 显示 App 层发现的拓扑和轨迹候选，并要求用户分别确认。 |
| `templates.py` | 模板选择、加载和保存交互。 |
| `theme.py` | 平面化主题、调色板和样式表。 |
| `fonts.py` | 字体选择和配置应用。 |
| `layout.py` | 尺寸、间距和布局辅助。 |
| `menu.py` | 顶部菜单和动作连接。 |
| `__init__.py` | 保持轻量，避免导入即启动 Qt。 |

批量 plot series 按配置逐项执行，以 `PlotModel` 合并展示。首次运行若尚无项目，GUI 在
轨迹目录创建/选择项目，再通过项目用例提交结果。恢复结果时，数值数据来自结果文件，
配色、坐标范围和可见性来自绘图状态，两者不互相污染。

GUI 的 New Project 先选择目录，由 App 层非递归发现受支持的拓扑和轨迹候选，再要求用户
在两个独立选项框中明确选择输入。取消目录或候选选择时保留当前工作区；确认后才清空会话、
填入输入并自动检查，首次有效分析按上述规则物化项目。Open Project 选择明确的
`mdhelper-project.json` manifest，成功校验 manifest 和输入后才替换当前会话。自动打开轨迹
目录中的既有项目时会先比较输入指纹，禁止把另一套体系的结果提交到该项目。

GUI 与 TUI 使用同一个 Backend 选择器。Energy 始终可通过 MDAnalysis 使用；显式
GROMACS RDF/CN 需要 `rdf` capability，通用 GROMACS trajectory adapter 需要 `trjconv`，
GROMACS Energy 需要 `energy`。
Backend 选择不参与体系检查；切换 Backend 不触发 Species 或 Index groups 刷新。

## 14. 外部工具：`integrations` 与 `runtime`

`integrations/gromacs.py` 定义 GROMACS 候选可执行名、环境键、版本/能力解释和领域身份。
它说明“GROMACS 是什么以及如何识别”，不直接实现通用子进程控制。

| 文件 | 职责 |
| --- | --- |
| `runtime/detection.py` | 以参数列表、受限环境、无 shell 和超时检测可执行文件，解析身份、版本和能力。 |
| `runtime/execution.py` | 使用显式 argv/cwd、可控交互 stdin、捕获输出；取消时先 terminate、等待后再 kill，超时时直接 kill，并记录软件身份、退出码、耗时和输出哈希。 |
| `runtime/environment.py` | 构造可控子进程环境，避免无关用户环境改变行为。 |
| `runtime/logging.py` | 在平台用户日志目录初始化日志；可由 `MDHELPER_LOG` 覆盖，失败时退化为 `NullHandler`。 |

外部工具运行记录可以写入项目 `integration_runs` 审计历史。显式 GROMACS RDF/CN 通过
Integration 调用 `gmx rdf`/`-cn`；GROMACS Energy 调用 `gmx energy`。任何对结果有贡献的
命令都在结果中显示软件正式名称、版本、可执行文件和
子命令。非零退出保留结构化记录，由调用用例决定如何呈现。

## 15. 模板、资源与文档契约

`resources/templates/` 保存随包发布的只读模板。模板通过 services 层发现并转换为 core
模板对象，表现层不直接猜测安装路径。用户模板与内置模板分开存储，保存行为是原子的。

| 位置 | 含义 |
| --- | --- |
| `schemas/analysis-request-v1.schema.json` | 分析请求的外部 JSON 结构。 |
| `schemas/analysis-result-v1.schema.json` | 分析结果的外部 JSON 结构。 |
| `schemas/project-v1.schema.json` | 项目 manifest 的外部 JSON 结构。 |
| `docs/methods/` | 公式、参数和算法定义。 |
| `docs/validation/` | 参考体系、期望值和验证结论。 |
| `docs/ALGORITHM.md` | 当前数值与确定性工程算法的集中说明。 |
| `docs/KNOWN_LIMITATIONS.md` | 当前未实现或尚未充分验证的边界。 |
| `docs/SELECTIONS.md` | 支持的选择来源和限制。 |
| `docs/SPECIES.md` | 角色建议与确认语义。 |
| `docs/CONFIGURATION.md` | 配置字段和路径规则。 |

`pyproject.toml` 把模板、schemas、方法、验证和用户文档纳入发行物。添加运行时资源时，
必须同时更新 package data/data files 和冻结打包配置，不能只让源码工作区可见。

## 16. 端到端数据流

```text
paths + reader mode
  -> trajectory dispatcher
  -> TrajectorySource
  -> SystemSummary
  -> optional NDX/static selections
  -> role suggestions
  -> presentation review
```

输入检查可以帮助用户理解体系，但不会产生隐式分析参数。

```text
validated AnalysisRequest
  -> source
  -> input hashes and environment provenance
  -> registered analysis function
  -> fixed selection indices
  -> frame iteration + PBC + chunked distances
  -> validated AnalysisResult
  -> optional project commit/export
```

```text
mdhelper-project.json result entry
  -> safe path resolution
  -> file hash verification
  -> AnalysisResult parsing
  -> PlotModel grouping
  -> CLI export or GUI rendering
```

项目恢复不重新运行分析算法，所以结果文件、hash 和 schema 校验是完整性关键。

## 17. 错误、日志和失败原子性

底层在最接近原因的位置抛出有类别的错误，应用层补充用例上下文，表现层只负责呈现：
CLI 输出稳定错误 JSON/退出码，不把进度混入 stdout；TUI 在当前菜单显示可恢复错误；
GUI 在主线程显示对话框并保留会话；日志记录技术细节，但不作为程序间契约。

文件保存和项目提交使用临时文件加原子替换；长任务取消不会发布半成品；输入哈希和结果
哈希在恢复时重新验证。这三层共同实现失败原子性。

## 18. 性能与并发模型

- 轨迹按帧迭代，不整体载入内存；
- pair distances 按配置上限分块；
- GUI 默认只有一个分析工作线程；
- 哈希按固定块读取；
- 绘图只消费结果数组，不保留完整轨迹。

不得在表现层额外启动不受 `TaskService` 管理的分析线程。若未来增加并行帧计算，必须保持
直方图归并顺序、进度、取消、内存上限和结果可复现性，并增加跨线程数数值测试。

## 19. 测试架构

- core/contract 测试验证严格解析、单位和绘图模型；
- backend/io 测试验证 GRO、MDAnalysis、NDX 和导出边界；
- analysis 测试验证 RDF、CN、PBC 和溶剂化计数；
- project 测试验证原子提交、严格拒绝旧字段、hash 和 schema；
- application/CLI/TUI/GUI 测试验证共享用例和交互状态；
- runtime 测试验证探测、超时、取消和退出记录；
- architecture 测试防止层间依赖倒置；
- packaging smoke 测试验证安装/冻结产物可启动并包含资源。

Linux 必须能在没有 Qt 的环境运行 CLI/TUI 和非 GUI 测试；Windows 额外验证 GUI 与冻结
产物。跨平台等价指相同请求、帧集合、算法和结果数据，不要求窗口渲染像素一致。

## 20. 扩展规则

### 20.1 新增分析

1. 在 core 契约中定义通用、版本化的数据字段；
2. 在 `analysis` 实现不依赖表现层的纯分析函数；
3. 注册到 `AnalysisRegistry`；
4. 在 app 用例中增加必要编排；
5. 各表现层只负责构造相同请求；
6. 增加方法、验证、schema、导出和跨前端测试。

### 20.2 新增轨迹后端

实现 `TrajectorySource`，完成单位转换、盒矩阵、原子身份和帧范围测试，再加入 dispatcher。
`auto` 规则必须确定且可解释，禁止捕获任意异常后无提示回退。

### 20.3 新增表现层

只依赖 `ApplicationService` 和允许展示的 core 类型。不得直接导入 `analysis`、`backends`
或另一表现层，不得实现第二套选择、项目提交或分析算法。

### 20.4 新增外部工具

在 `integrations` 描述软件候选和能力，并由 manager 统一检测、状态管理和执行；在
`runtime` 复用安全执行原语，在 app 暴露用例。不得把外部工具文本输出当作内部稳定契约。

## 21. 工程师修改检查表

- 依赖方向是否仍满足架构测试；
- 请求、结果、Python 校验器与 JSON Schema 是否同步；
- 单位转换是否只发生在明确边界；
- 选择、角色、参数决策和帧审计是否进入 request/diagnostics/provenance 的相应位置；
- 新循环是否有资源上限、进度和取消点；
- 文件写入是否原子，项目恢复是否验证 hash；
- CLI/TUI/GUI 是否仍调用同一应用用例；
- 新行为是否有方法说明、验证证据和已知限制；
- 新资源是否进入 wheel 和 Windows 冻结产物；
- 实现是否通用，未针对文件名、类名、测试名、样例或具体软件输出写特判。

这套边界的核心是让每种算法只有一个事实来源，让所有入口产生可复现、可审计、可恢复
的同一种结果，同时使 I/O、第三方库、GUI 和外部程序停留在可替换的外层。
