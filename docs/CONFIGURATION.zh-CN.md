# MDHelper 配置

[English](CONFIGURATION.md) | [简体中文](CONFIGURATION.zh-CN.md)

MDHelper 使用带 schema version 的 TOML 文件。

配置解析顺序如下：

1. CLI `--settings`。
2. `MDHELPER_CONFIG`。
3. macOS 统一使用 `~/.config/mdhelper/config.toml`（源码与 `.app` 启动一致）；其他情况使用可执行程序或 Python runtime 同目录的 `config.toml`。

macOS 从 **MDHelper > Settings…**（**⌘,**）打开配置，Windows/Linux 保持原有菜单栏 **Settings** 入口。配置会交给系统默认的 TOML 编辑器；文件不存在时自动创建。`mdhelper config path` 可查询实际路径。旧的 `~/Library/Application Support/MDHelper/` 或 Python 同目录配置不会自动迁移；需要时手动复制到新路径，或用 `MDHELPER_CONFIG` 保留旧路径。

## GUI

GUI 外观存入共享配置：

```toml
[gui]
theme = "system" # system, light, dark
font_size = 11.0 # 6 到 32 pt，不含 Workspace 文本编辑区
workspace_font_family = "" # 自动选择平台等宽字体
workspace_font_size = 14.0 # 6 到 32 pt，独立于 font_size
```

**View > Appearance** 应用并保存主题，`system` 跟随操作系统配色。应用字号通过配置中的 `font_size` 修改，重启后生效。

`workspace_font_family` 和 `workspace_font_size` 仅作用于 Workspace 文本编辑区及行号，包括只读文本预览；修改后重启生效，切换主题不会覆盖。字体名必须为字符串：空字符串表示自动选择，非空名称忽略首尾空白并按不区分大小写匹配已安装字体，不接受仅含空白的名称。未指定或指定字体不存在时，Windows 优先使用已安装的 Consolas，否则回退到系统等宽字体；其他平台回退到系统等宽字体。两个字号字段都接受 6 到 32 pt 的有限数值，不接受字符串或布尔值。缺少新字段的旧配置使用自动字体和独立的 14pt 字号，不再随全局字号增大。这些设置不影响菜单、其他控件、绘图、图片或数据表预览。

Workspace 文本编辑区行距为字体自然行高的 1.35 倍，制表符宽度为四个空格，随字体一起重新计算行号区域宽度。这些设置仅影响显示，不改变文件内容或撤销记录。行号绘制在文档之外，不写入保存的文件。底部显示从 1 开始的行列位置和选中字符数。列按 Unicode 码点计数，制表符每四列对齐；选区中的换行计为一个字符。图片与数据表预览不显示文本光标位置。

Workspace 按内容识别文本，不根据扩展名特判。文本直接显示原文，不转成解析表格；超过 1 MiB 时显示明确标注的只读原文预览，仅包含前 1 MiB，禁用保存以防截断源文件。图片保持图片预览，只有二进制数据交给科学数据读取器。

**Export Text...** 默认导出 UTF-8 CSV（逗号分隔），保留 TXT（制表符分隔），不再提供 TSV。EDR 导出包含 Frame、Time 和已勾选的 term，表头保留单位，并包含全部帧。搜索过滤不改变勾选状态；至少勾选一个 term 才能导出，使用点击导出时的选择。

## Workflow

命名 workflow 包含有序的分析项目标识：

```toml
[workflows]
radial = ["rdf", "cumulative_rdf"]
full = ["rdf", "cumulative_rdf", "energy"]
```

支持 `rdf`、`cumulative_rdf` 和 `energy`，同一项目可以重复出现。**Tools > Run Workflow...** 按照配置顺序打开每个项目供用户审查，然后通过标准分析队列提交完整序列。

## 分析 Backend

每个 request 选择 `auto`、`mdanalysis` 或 `gromacs`。该值属于 request，不是全局设置。它固定输入加载、选择语法、帧处理和计算。Auto 先考虑 MDAnalysis，再考虑可用的 GROMACS 管线。显式选择不回退。

## Integration

所有 Integration 使用以下结构：

```toml
[integrations.gromacs]
enabled = true
path = ""
search_paths = []
use_environment = true
detect_timeout_seconds = 10.0
run_timeout_seconds = 3600.0
```

`path` 和每个 `search_paths` 条目都标识可执行文件。`use_environment = false` 关闭 adapter 环境候选，但保留配置路径和 `PATH`。Disabled Integration 不产生自动候选，但仍接受本次运行路径。

候选按规范路径去重，并按以下顺序检测：

1. 本次运行路径。
2. 配置的 `path`。
3. 配置的 `search_paths`。
4. Adapter 环境路径。
5. `PATH` 中的注册名称。
6. Adapter 平台路径。

GROMACS 使用 `MDHELPER_GROMACS`、`GMXBIN` 下的候选，以及 `PATH` 中的 `gmx` 或 `gmx_mpi`。VMD 使用相同契约和自己的候选。

检测验证身份、版本和 capability。执行使用 argv、`shell=False`、工作目录、受限环境、超时、取消和 run record。记录包含 executable、版本、argv、工作目录、环境摘要、exit code、捕获的 stream、耗时、状态和输出 hash。GROMACS 是可选依赖，不同受支持版本的外部 Backend 结果可能存在差异。

Windows **Tools > Integrations** 编辑并检测 Integration。当前会话检测成功或保存路径非空后，分析选择器显示 GROMACS。

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
