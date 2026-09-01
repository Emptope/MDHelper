# MDHelper 配置

[English](CONFIGURATION.md) | [简体中文](CONFIGURATION.zh-CN.md)

MDHelper 使用带 schema、可编辑的 TOML 用户配置。支持的外部软件统一放在
`[integrations.<name>]` 下；候选名、环境路径、版本解析和 capability 检测由注册 adapter
提供。默认注册表包含 GROMACS 和 VMD。

默认将 `config.toml` 放在当前可执行程序或 Python runtime 同目录：

```text
<可执行程序目录>/config.toml
```

自动化和测试可用 `MDHELPER_CONFIG` 指向其他文件。机器相关的可执行文件路径只属于用户
配置，不能写入可移植项目 manifest。

每个平台归档都在唯一可执行程序旁提供 `config.toml`。所有冻结程序都自动使用该文件，因此可以
直接编辑配置并整个移动目录。CLI `--settings` 和用户已设置的 `MDHELPER_CONFIG` 优先于默认位置。

诊断日志位于平台用户日志目录；`MDHELPER_LOG` 可显式选择文件。日志写入是本地、尽力而为
的辅助能力，失败时不能覆盖原始用户错误。

## GUI 外观

GUI 默认跟随操作系统配色。可在 **View -> Appearance** 选择 System、Light 或 Dark，设置会
立即生效并保存：

```toml
[gui]
theme = "system" # system, light, dark
font_size = 11.0 # 6 到 32 pt
```

三种模式使用相同的 Qt 平台控件风格，因此切换配色不改变布局尺寸。System 会恢复平台
palette 并继续响应系统配色变化。

## Backend

每个分析请求只选择一个 `auto`、`native`、`mdanalysis` 或 `gromacs` Backend。它不是全局
TOML 设置，因为它决定源数据读取方式，并影响格式支持、单位和可复现性。选择值出现在设置
复核中并进入 request。`auto` 对双 GRO 优先 native，对其他受支持轨迹和 EDR 优先
MDAnalysis；MDAnalysis EDR 支持不可用时，Energy 可回退到可用 GROMACS。显式选择不回退。
选择 `gromacs` 运行 RDF/CN 时由 `gmx rdf`/`-cn` 生成曲线；运行 Energy 时由
`gmx energy` 提取序列。RDF/CN 把原 topology 和 trajectory 直接传给 `gmx rdf`；只有
stride 帧范围通过 `gmx trjconv -fr` 生成精确的临时 XTC 子集，`gmx rdf` 仍使用原
topology。

## 最初版本的严格契约

0.1.0 是最初契约。项目 request 和 plot state 必须精确符合当前 schema；未知、缺失或已
废弃的开发期字段直接报错，不做数据迁移。

## Integration 配置与检测

所有 integration 使用同一组字段：

```toml
[integrations.gromacs]
enabled = true
path = ""
search_paths = []
use_environment = true
detect_timeout_seconds = 10.0
run_timeout_seconds = 3600.0
```

`path` 是首选完整可执行路径。`search_paths` 的每一项是额外可执行候选，不是待扫描目录。
`use_environment = false` 只关闭 adapter 环境路径，不关闭配置路径或 `PATH`。两个 timeout
均为正秒数。disabled integration 不加入自动候选，但仍允许本次运行显式传入路径。

候选按以下稳定顺序检测，并按规范路径去重：

1. 本次运行的 `--path`；
2. `[integrations.<name>].path`；
3. 配置顺序中的 `[integrations.<name>].search_paths`；
4. adapter 环境路径；
5. 在 `PATH` 中解析注册命令名；
6. adapter 的平台候选路径。

GROMACS 环境路径包括 `MDHELPER_GROMACS` 中的完整路径，以及 `GMXBIN` 下的
`gmx`/`gmx_mpi`；这些命令名也会在 `PATH` 中解析。VMD 使用相同契约和自己的 adapter
候选。

每个候选必须通过 adapter 身份/版本与 capability 检测。`IntegrationStatus` 记录可用性、
所选路径、版本、capabilities、来源、错误和全部检测尝试。检测不会选择轨迹或分析 backend。
执行始终使用参数向量、`shell=False`、显式工作目录、受限环境、超时/取消和 integration
运行记录。

Windows **Tools > Integrations** 仅负责配置与检测。检测成功后会回填已配置的可执行文件
字段，并以可读字段显示状态、版本、来源和 capabilities。Detect 会使用对话框当前草稿，
包括尚未保存的 configured executable；保存会使旧检测缓存失效，下一次使用将按新配置
重新验证。Integration 命令由分析用例或显式 CLI 命令执行，不放在该配置对话框中。完成、非零退出、超时和取消都会记录软件
名称、可执行文件、版本、参数、工作目录、环境摘要、退出码、日志、耗时、状态和指定输出文件指纹。

## 命令

```bash
mdhelper config path
mdhelper config init
mdhelper config check
mdhelper config show
mdhelper integrations list
mdhelper integrations detect gromacs
mdhelper integrations run gromacs -- --version
mdhelper templates list
```
