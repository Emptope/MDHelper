# MDHelper 软件设计目标

[English](SOFTWARE_DESIGN_GOALS.md) | [简体中文](SOFTWARE_DESIGN_GOALS.zh-CN.md)

以下约束适用于 MDHelper 0.1.0。0.1.0 不兼容此前的开发期 API、schema 或行为。契约变更必须
同步修改生产者、消费者、schema、测试和文档，不保留迁移分支。

## 优先级

1. 方法正确性和可复现性。
2. 数据完整性和失败处理。
3. 显式控制和可操作错误。
4. 资源上限和取消。
5. 各界面行为一致。
6. 可维护性。
7. 展示。

## 约束

| ID | 约束 | 验收 |
| --- | --- | --- |
| G1 | 已发布分析包含方法、契约、Backend 支持、应用用例、界面、持久化、导出、测试和文档。 | 端到端运行可从项目加载并导出通过验证的结果。 |
| G2 | 科学公式只位于分析层和带版本的方法文档。 | 参考测试覆盖 PBC、网格、归一化和 self exclusion；界面不包含公式。 |
| G3 | 依赖遵循[架构](ARCHITECTURE.zh-CN.md)。 | `tests/test_architecture.py` 通过。 |
| G4 | 选择、参数、帧范围、Backend 和确认后的角色是显式 request 数据。 | 校验覆盖每个存储值；角色建议只存在于当前 session，且不存在输入名称特判。 |
| G5 | 建议提供证据，且不修改源数据或参数。 | unavailable 和 low confidence 不影响主分析结果。 |
| G6 | Result 带版本、严格且自描述。 | Runtime parser 和 JSON schema 拒绝未知、缺失或不一致字段。 |
| G7 | Result 标识输入、环境、选择、参数、帧和实际 Backend。 | SHA-256 检测内容变化并支持项目重定位。 |
| G8 | 项目持久化具有失败原子性。 | 写入失败后旧项目仍可读，且不发布部分结果。 |
| G9 | 工作按帧或块流式处理并支持取消。 | 内存不随轨迹帧数增长；取消不提交结果。 |
| G10 | 一个 Backend 负责一次完整尝试。 | 显式 Backend 不回退；Auto 回退不混用组件。 |
| G11 | CLI、TUI 和 GUI 调用相同应用用例。 | 等价输入生成等价 request 和 result。 |
| G12 | Plot state 与 result 数据分离。 | 预览和导出使用同一模型；样式不修改 result array。 |
| G13 | 外部程序通过 Integration 边界运行。 | 命令使用 argv、`shell=False`、超时、取消和 run record。 |
| G14 | 配置和模板使用经过验证的契约。 | Wheel 和冻结程序无需源码目录即可读取资源。 |
| G15 | 错误提供类别和操作，不依赖文本解析。 | 界面区分输入、方法、取消、Integration 和内部错误。 |
| G16 | 扩展工作位于声明的边界。 | 新功能使用注册表和协议，不复制现有调用链。 |

## 当前决策

| 主题 | 决策 |
| --- | --- |
| 入口 | 无参数时先选择 GUI，再选择 TUI；显式模式选择 GUI、TUI 或 CLI。 |
| Backend | MDAnalysis 和 GROMACS 是完整管线；GROMACS 可选。 |
| 选择 | MDAnalysis 使用 NDX 或静态 expression；GROMACS 使用 NDX 或原生 expression。 |
| 参数 | Request 包含径向限制、bin width、帧范围和 Backend。 |
| 建议 | ITP 推断的物种角色和第一壳层边界需要确认，且不修改计算。 |
| 项目 | JSON manifest 索引带 hash 的输入和 result 文件。 |
| Job | 默认使用一个 worker；取消为协作式。 |
| 绘图 | 支持 residue-name 和固定配色；plot state 持久化。 |
| 统计 | 基础方法不报告 uncertainty。 |
| Cache | Cache 数据可重建；分析结果不缓存。 |
| 产物 | 每个 wheel、executable 和 archive 不超过 256 MB。 |

## 发布门槛

- 带版本的方法文档与计算代码和验证证据一致。
- PBC、变盒、重叠选择、帧范围和非法输入有测试。
- Request、result、project、plot 和配置 schema 与 runtime 校验一致。
- 原子写入、取消、进程失败和项目损坏有测试。
- CLI stdout 可由程序读取；TUI 和 GUI 保持响应且支持 headless 环境。
- Linux 和 Windows 测试、Ruff、mypy 和源码 ASCII 检查通过。
- Wheel 和冻结构建审计包含声明资源并拒绝遗留模块。
- 每个便携归档在目标平台通过启动和资源 smoke test。

## 评审问题

1. 修改了哪个契约或用例？
2. 公式、单位、PBC、选择或帧采样是否变化？
3. 所有界面是否构造相同语义的 request？
4. 新默认、建议或 fallback 是否进入 provenance？
5. Runtime 校验和 schema 是否一致？
6. 内存、进度、取消和失败行为是否有界？
7. 写入失败是否会暴露部分状态？
8. 每个依赖是否位于所属包？
9. 新资源是否进入发布产物？
10. 方法、验证、限制和用户文档是否与实现一致？
