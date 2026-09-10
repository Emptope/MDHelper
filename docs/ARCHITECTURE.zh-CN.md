# MDHelper 软件架构

[English](ARCHITECTURE.md) | [简体中文](ARCHITECTURE.zh-CN.md)

## 包职责

| 包 | 职责 |
| --- | --- |
| `bootstrap` | 统一 CLI/TUI/GUI 分派及便携配置 |
| `cli`、`tui`、`gui` | 输入与呈现；调用应用功能，不直接调用 backend |
| `app` | 用例编排、导出计划与报告 |
| `jobs` | 进度、执行状态与协作取消 |
| `core` | 领域契约、错误、单位与绘图模型，不依赖 adapter |
| `analysis`、`backends` | 完整分析管线、输入加载与选择 |
| `services` | 配置、检查、provenance 与模板 |
| `integrations`、`runtime` | 外部工具、环境过滤、进程生命周期与日志 |
| `project`、`io` | Manifest、指纹、存储、解析与导出 |

只有 bootstrap 装配呈现层。Qt 限于 `gui`，状态模型不要求 Qt。分析不能依赖呈现或绘图；进程对象留在 integrations 和 runtime 边界内。避免循环导入及持久化层反向依赖编排层。

## 分析流程

```text
request -> validation -> backend resolution -> input loading and static selection
        -> provenance -> execution -> result validation -> export or project commit
```

`app/facade.py` 是装配入口。`analysis/pipeline/` 的每个注册项负责一次完整 backend 尝试。自动回退不会混用不同 backend 的输入加载与计算；显式选择 backend 时不回退。

`core/analysis/` 定义 schema-1 请求和结果。`RadialRequest` 用于 RDF 与累计 RDF，`EnergyRequest` 用于 EDR 序列。结果包含请求、数组、单位、诊断、provenance 和方法版本。预览与导出共用 `core/plotting/` 模型。

## 存储与 Job

```text
project/
|-- mdhelper-project.json
|-- results/
|   |-- data/
|   `-- runs/
|-- figures/
`-- cache/
```

Manifest 索引输入、已确认角色、结果及绘图状态；完整结果 JSON 保存数据和 provenance。派生路径必须位于项目内，加载时验证身份、哈希与 schema。写入采用同目录临时文件和原子替换；Manifest 提交失败时删除新写入但未索引的结果。缓存均可重建。

Job 从 pending 进入 running，最终为 completed、failed 或 cancelled。帧边界、哈希分块和进程轮询检查取消。GUI worker 向 Qt 线程报告状态；外部命令使用参数数组、超时、输出捕获和进程组终止。

## 开发检查

```bash
uv sync --frozen --extra gui --group dev
uv run prek run --all-files
uv run pytest -q --cov=mdhelper
```

Linux 可增加 `-n 4 --dist worksteal`；macOS 和 Windows 串行运行 Qt 测试。测试默认使用 offscreen Qt，`QT_QPA_PLATFORM=cocoa` 可启用 macOS 原生检查。优先保留行为回归和代表性边界，不穷举样式与字体组合，也不重复检查第三方绘制或构建命令文本。原生安装包 smoke test 由 Quality CI 执行；覆盖率门槛保持 80%。

Linux/macOS 内存分析可安装 `--group profile`，再通过 `uv run --group profile memray run --native -m mdhelper` 运行代表性命令。

算法、配置和发布契约分别见[算法说明](ALGORITHM.zh-CN.md)、[配置](CONFIGURATION.zh-CN.md)和[打包](PACKAGING.zh-CN.md)；用户流程见[使用说明](USAGE.zh-CN.md)。
