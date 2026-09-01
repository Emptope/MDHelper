# MDHelper

[English](README.md) | [简体中文](README.zh-CN.md)

MDHelper 0.1.0 是一款用于 GROMACS 分子动力学数据的本地可复现后处理应用。它通过引导式
终端界面、适合自动化的 CLI 和 Windows 桌面 GUI，提供径向分布函数（RDF）、GROMACS 式
累积 RDF（界面显示为 Cumulative Coordination Number，CN）和 EDR
energy 数据提取。

> MDHelper 目前是 0.1.0 alpha 开发版本。

## 主要特性

- TUI、CLI 和 GUI 共用同一套分析实现；
- 以流式方式分析大型轨迹，并限制成对距离计算的内存占用；
- 提供互不混用的 Native、MDAnalysis 和可选 GROMACS 三条完整分析流水线；
- Native 使用 MDHelper GRO Reader 和精确 NDX 组，MDAnalysis 支持更多轨迹格式与静态表达式，
  GROMACS 使用自身完成输入处理和分析；
- 支持正交和三斜周期性边界条件；
- 提供可移动、可校验输入指纹的项目，集中保存结果数据、分析历史和绘图状态；
- 导出完整 JSON 元数据、CSV 数据与 PNG/SVG/PDF 图像；
- 通过统一的 Integrations 注册表检测并受控执行 GROMACS 和 VMD，记录状态与能力。

## 使用入口

| 界面 | 命令 | 用途 | 正式支持的平台 |
| --- | --- | --- | --- |
| TUI | `mdhelper tui` | 引导式交互分析 | Linux、Windows |
| CLI | `mdhelper <command>` 或 `mdhelper cli <command>` | 脚本与自动化 | Linux、Windows |
| GUI | `mdhelper` 或 `mdhelper gui` | 桌面项目、分析与绘图 | Windows；Linux 可选 |

不带参数执行 `mdhelper` 时，Qt 和 display 可用则优先打开 GUI，否则降级到编号式 TUI。
显式 `gui`、`tui`、`cli` 可选择界面，其他参数进入 CLI。TUI 的多级菜单使用 `0` 返回，
并在分析开始前集中显示设置供用户确认。workspace 未加载时，首页显示当前 project/workspace
状态且只提供 Load 菜单；加载后主菜单仅保留 Analysis、Results、Workspace 和 Tools。Tools
中的 Integrations、Templates 和 Configuration 保持为独立入口。未打开项目时，默认导出
目录是所选 trajectory 旁的 `results/<analysis-type>`；项目 workspace 使用
`<project>/exports/<analysis-type>`。

## 环境要求与安装

从源码开发需要 Python 3.12 或更高版本，以及
[`uv`](https://docs.astral.sh/uv/)：

```bash
uv sync --group dev
uv run mdhelper --version
```

在源码目录中启动各界面：

```bash
uv run mdhelper
uv run mdhelper --help
uv run mdhelper gui
uv run mdhelper tui
```

发布包按平台归入 `dist/linux` 和 `dist/windows`，两者都是便携归档。Linux x86_64 包只含
一个独立 `mdhelper` 程序。它内置 CLI、TUI 和
Python runtime，不包含 Qt，也不要求用户安装 Python。解压后可直接运行 `./mdhelper`、
`./mdhelper tui` 或 `./mdhelper cli --help`。Linux GUI extra 只用于可选的源码开发和测试。

Windows x64 包是只含一个 `mdhelper.exe` 的 ZIP。解压后请将该程序与 `config.toml`
保持在同一目录。它不需要安装或管理员权限；任何发布
可执行程序或发布归档超过 256 MB 都会构建失败。构建和验证说明见
[打包与发布验证](docs/PACKAGING.zh-CN.md)。

## 快速开始

在选择分析组之前检查体系：

```bash
uv run mdhelper inspect \
  --topology topol.tpr \
  --trajectory md.xtc \
  --index index.ndx
```

使用精确的 NDX 组名计算 RDF：

```bash
uv run mdhelper analyze rdf \
  --topology topol.tpr \
  --trajectory md.xtc \
  --index index.ndx \
  --reference "Cations" \
  --selection "Solvent oxygen" \
  --analysis-backend gromacs \
  --r-max 1.0 \
  --bin-width 0.002 \
  --output results/rdf
```

使用 MDAnalysis 表达式计算累积 RDF 曲线：

```bash
uv run mdhelper analyze cumulative-rdf \
  --topology topol.tpr \
  --trajectory md.xtc \
  --reference "resname LI" \
  --selection "resname SOL and name O" \
  --analysis-backend mdanalysis \
  --r-max 1.0 \
  --bin-width 0.002 \
  --output results/cn
```

从 GROMACS energy 文件提取指定序列并绘制标准化结果：

```bash
uv run mdhelper analyze energy \
  --energy-file ener.edr \
  --terms '[Potential, Temperature]' \
  --output results/energy
```

GUI 和 TUI 选定或更换 EDR 文件后，都会通过所选 Backend 自动发现该文件实际包含的完整
term 菜单。`auto` 优先使用 MDAnalysis；只有 MDAnalysis 无法读取且已检测到 `gmx energy`
capability 时才回退到 GROMACS。用户从可选列表将 term 加入有序分析队列，无需手工输入
逗号分隔的名称。

所有径向分析命令还支持 `--start`、`--stop`、`--stride`、`--analysis-backend` 和
`--figures false`。

## 分析类型

| 分析 | 结果 | 主要显式参数 |
| --- | --- | --- |
| RDF | 半径与 `g(r)`；条件允许时给出可解释的第一配位壳诊断 | Reference、Selection、`r_max`、bin width、帧范围 |
| 累积 RDF（UI：Cumulative CN） | 半径与 `N(r)` | Reference、Selection、`r_max`、bin width、帧范围 |
| Energy | 时间与每个所选 EDR 项的标准化序列 | EDR 文件、energy 项、后端 |

版本化的方法定义与验证证据分别位于
[docs/methods](docs/methods/README.zh-CN.md) 和 [docs/validation](docs/validation/)。

## 输入与选择

Backend 表示包含文件 reader 在内的完整分析流水线：

| Backend | 完整流水线 |
| --- | --- |
| Native | MDHelper GRO Reader、精确 NDX 组、Native 帧迭代和径向距离计算 |
| MDAnalysis | MDAnalysis reader、NDX 组或静态 MDAnalysis 表达式、MDAnalysis 帧处理和径向距离计算，以及用于 Energy 的 `EDRReader` |
| GROMACS | NDX 组或 GROMACS selection expression、直接用于 RDF/CN 的 `gmx rdf`、抽样帧子集所需的可选 `gmx trjconv -fr`，以及用于 Energy 的 `gmx energy` |
| Auto | 为请求选择第一个可用的完整流水线，绝不组合不同 Backend 的组件 |

Native 支持单帧或多帧 GRO topology/trajectory 组合，并要求 NDX 文件。MDAnalysis 支持以
`.tpr` 或 `.gro` 为 topology、以 `.xtc` 或 `.trr` 为 trajectory。格式兼容性由所选流水线
的软件版本决定。默认全帧范围下，GROMACS 流水线把原 topology 和 trajectory 直接传给
`gmx rdf`。显式有限抽样帧范围只运行一次 `gmx trjconv -fr`，生成精确零基帧索引的临时
XTC，`gmx rdf` 保留原 topology。

GROMACS 按原子索引将 structure/topology 与 XTC 轨迹对应。XTC 提供按顺序排列的
坐标、原子数、step、time 和 box；原子与残基元数据来自 structure/topology。GROMACS
通常只检查这两类输入的原子数，因此原子数相同不能证明原子顺序相同。MDHelper
遵循这一规则，不根据 `em`、`npt` 或 `md` 等文件名猜测配对；应选择同一系统且
原子顺序未变的 structure 快照。如果有匹配的 TPR，`gmx check -f trajectory.xtc -s1
topology.tpr` 还可通过键长异常发现部分顺序问题。详见 GROMACS 官方的
[selection 输入语义](https://manual.gromacs.org/current/onlinehelp/selections.html)、[XTC
格式](https://manual.gromacs.org/current/reference-manual/file-formats.html#xtc) 与 [`gmx
check`](https://manual.gromacs.org/current/onlinehelp/gmx-check.html)。

提供 `--index` 后，每个选择参数都是区分大小写的精确组名；Native 要求使用该模式。
没有 index 文件时，MDAnalysis 使用静态 MDAnalysis atom-selection expression，GROMACS
RDF/CN 使用 GROMACS selection expression。

开始流式读取轨迹之前，所有选择都会解析为固定的原子身份。因此程序会拒绝 `around`、
`sphzone`、`prop` 等依赖坐标的表达式。支持的语法与校验规则见
[原子与组选择](docs/SELECTIONS.zh-CN.md)。

## 项目与导出

项目会集中保存输入指纹、已确认的物种角色、已完成结果、integration 运行记录和绘图状态。
每份完整结果仅在 `results/data/` 下保存一次并校验指纹：

```text
analysis-project/
  mdhelper-project.json
  results/
    data/
      <analysis-id>.json
  figures/
  cache/
```

通过 CLI 创建并检查项目：

```bash
uv run mdhelper project create \
  --path analysis-project \
  --topology topol.tpr \
  --trajectory md.xtc \
  --index index.ndx

uv run mdhelper project show --path analysis-project
```

项目路径必须不存在或为空。向 `inspect` 或 `analyze` 子命令传入
`--project analysis-project`，即可在适用时复用经过校验的输入，并在成功后提交结果。
Energy 提交会把 EDR 文件作为带指纹的 `energy` 输入加入项目。项目可以移动；只有输入
文件的 SHA-256 指纹仍然匹配时，MDHelper 才会重新连接这些文件。项目运行的全部 GROMACS
命令工作目录和生成的源输出统一保留在当前项目的 `cache/` 目录下。

Windows GUI 的 **File > New Project** 会发现所选目录直属的 `.tpr`/`.gro` topology、
`.xtc`/`.trr`/`.gro` trajectory 和可选 `.ndx` 文件。仅有一个索引候选时会自动
选中，有多个候选时由用户明确选择。更改
所选 topology、trajectory 或 index 文件后，界面会自动重新加载 Species 和 Index groups，
无需额外的检查按钮。体系检查使用自动内置 reader 策略，与分析所选 Backend 无关；
仅切换 Backend 不会重新加载体系。第一次有效分析会在轨迹旁生成就地项目。
**File > Open Project** 会显式打开 `mdhelper-project.json`，校验输入后恢复角色、结果与绘图状态。

直接分析导出包含完整的 `result.json`、对应分析的 CSV 文件，以及默认生成的 PNG、SVG、
PDF 图像。GROMACS 结果还会导出 `gmx rdf` 或 `gmx energy` 生成的未经修改的 XVG 文件。
每次 integration 运行的完整执行命令都会写入 `result.json` 和诊断日志；运行时进度只把
最新一行原生输出包装为 `GROMACS: ...`，不显示完整命令。JSON 与 CSV 数值采用稳定的
15 位有效数字格式；PNG 使用 300 DPI，SVG 和 PDF 保持矢量格式。

GUI 可以比较多个兼容结果，将 RDF 和 CN 组合在共享距离轴及独立 Y 轴上，编辑图例与
颜色，设置显式坐标范围，保存绘图组合，并恢复项目中已保存的结果。每个选中的 GROMACS
energy term 默认各自在独立窗口中绘图，一个窗口只显示一张图；在 **Plot series** 中选择
energy 行并使用 **Combine** 可将其绘制到同一窗口的共享坐标轴，**Separate** 可恢复独立
绘图窗口。组合行会在 Plot 列显示 `Combined` 标记；组合关系会保存在项目绘图状态和图像
导出中。

TUI 分析菜单也提供 **RDF + CN Combined Plot**。它让两项分析复用同一套径向配置，分别保存
原始结果，并输出一套合并的 PNG/SVG/PDF 图像。

## 方法与可复现性约定

- 持久化距离单位为 nm，时间单位为 ps；径向图的横轴会把存储的 nm 转换为埃显示。
- RDF 和累积 RDF 基础结果是所选帧上的确定性结果；energy 结果保留用户显式选择
  的 EDR 序列。
- 0.1.0 schema 是严格的最初契约；已废弃的开发期字段会被拒绝，不做迁移。
- 基础结果不估计平衡时间、自相关、收敛性、不确定度或标准误。
- 物种角色建议是可解释且需要确认的元数据，不会改变选择、cutoff 或数值算法。
- 第一配位壳检测是分析后的诊断，不会改变曲线。
- 请求、结果、输入文件、后端决策、软件版本、选择和帧审计都会写入 provenance。

使用生产数据前请阅读[已知限制](docs/KNOWN_LIMITATIONS.zh-CN.md)。

## Integrations

注册表当前支持 GROMACS 和 VMD。显式选择 GROMACS trajectory、RDF/CN、Energy 后端或
执行受控 integration 时需要 GROMACS；MDAnalysis 可以直接读取 EDR，无需 GROMACS
可执行程序：

```bash
uv run mdhelper config init
uv run mdhelper integrations list
uv run mdhelper integrations detect gromacs
uv run mdhelper templates list
```

仅当用户在当前会话的 Integrations 中显式执行过 GROMACS 检测，或已保存 configured
executable 路径时，Analysis Settings 的 Backend 选择器才显示 GROMACS；该可执行文件通过
capability 检测后选项才可用。GROMACS RDF/CN 需要 `rdf` capability，抽样帧子集额外需要
`trjconv`；GROMACS Energy 需要 `energy`。
没有 GROMACS 时，Energy 仍可通过 Auto 或 MDAnalysis 使用。Load 和体系检查不显示该
选择器，也不会因分析 Backend 改变而重新加载。

检测使用稳定优先级：单次运行的 `--path`、`[integrations.<name>].path`、配置的
`search_paths`、adapter 环境路径、`PATH`、平台候选路径。GROMACS 的环境来源包括
`MDHELPER_GROMACS` 和 `GMXBIN`。状态会记录可用性、所选路径、版本、capabilities、来源和
全部检测尝试。径向请求的 Auto 仅在 GRO/GRO 加 NDX 时先尝试 Native，随后是 MDAnalysis，
最后是可用的 GROMACS 流水线；Energy 先尝试 MDAnalysis，再尝试可用的 GROMACS 流水线。
source 加载失败时才进入下一条完整流水线，同一次尝试内绝不混用组件。结果同时记录请求的
Backend 和实际解析出的 Backend。Windows GUI 在
**Tools > Integrations** 仅负责软件配置与检测。检测成功后会回填可执行文件字段，
并以可读字段显示版本、来源和 capabilities。命令执行属于分析工作流或显式 CLI
命令，不放在该配置对话框中。**Tools > Templates** 继续提供内置文本资源。

配置位置、便携模式、环境变量覆盖与 integration 运行 provenance 见
[配置说明](docs/CONFIGURATION.zh-CN.md)。

## 开发与验证

运行源码质量检查：

```bash
uv run ruff check src tests
uv run mypy src
uv run pytest
```

设计与实现参考：

- [软件设计目标](docs/SOFTWARE_DESIGN_GOALS.zh-CN.md)
- [软件架构](docs/ARCHITECTURE.zh-CN.md)
- [算法说明](docs/ALGORITHM.zh-CN.md)
- [选择契约](docs/SELECTIONS.zh-CN.md)
- [物种角色](docs/SPECIES.zh-CN.md)
- [打包说明](docs/PACKAGING.zh-CN.md)

## 许可证

MDHelper 按 [GNU General Public License version 2](LICENSE) 分发，对应 SPDX 表达式
`GPL-2.0`。第三方依赖和未纳入仓库的模拟输入仍分别遵守其原有许可证。
