# MDHelper 使用说明

[English](USAGE.md) | [简体中文](USAGE.zh-CN.md)

## 环境

源码开发需要 Python 3.12 或更高版本及[`uv`](https://docs.astral.sh/uv/)：

```bash
uv sync --group dev
uv run mdhelper --version
```

`uv run mdhelper` 自动选择 GUI 或 TUI。使用 `gui`、`tui` 或 `cli` 指定界面。使用 `uv run mdhelper --help` 查看命令参数。

## Workspace 文件浏览

打开文件夹即可浏览，不改变分析输入。文件名位于内容上方，大小、修改时间、格式或读取状态位于下方。

- 二进制表格随滚动按需加载，只将已访问行写入磁盘缓存，GUI 保留有限页缓存。滚动条范围随已加载行数增长，不要求使用帧选择器或手动点击下一页。
- XTC/TRR 顺序读取，不在打开时扫描完整帧索引；EDR 使用只读内存映射，按需解析帧，不预先分配全部能量序列。其他解析器可能仍需读取格式元数据或一个完整首帧，但打开时不再导出全部记录。
- 不超过 1 MiB 的 UTF-8 文本保持可编辑；更大的文本仅显示前 1 MiB 的只读预览，禁止保存部分预览内容，避免覆盖原文件。
- 图片按内容识别，支持 PNG、JPEG、GIF、BMP、TIFF、WebP 等格式。显示时才在后台解码第一张图片，按视口适配并展示原始尺寸；合并连续缩放请求，离开页面释放像素缓存。显示解码每边最多 2048 像素；若解码器无法在完整展开超过 32 MiPixels 的原图前缩小图片，则报告内存限制，不强行加载。并非所有压缩图片格式都支持任意区域解码。

取消、切换文件或离开 Workspace 会停止待执行读取并丢弃过期结果。切换文件前仍会确认小文本的未保存修改。

## 检查与分析

选择分析组前检查输入：

```bash
uv run mdhelper inspect \
  --topology md.gro --trajectory md.xtc --index index.ndx
```

使用 NDX 组名运行 RDF：

```bash
uv run mdhelper analyze rdf \
  --topology md.gro --trajectory md.xtc --index index.ndx \
  --reference "<GROUP_NAME>" --selection "<GROUP_NAME>" \
  --analysis-backend gromacs --r-max 1.0 --bin-width 0.002 \
  --output results/rdf
```

使用 MDAnalysis expression 运行累积 RDF：

```bash
uv run mdhelper analyze cumulative-rdf \
  --topology topol.tpr --trajectory md.xtc \
  --reference "resname LI" --selection "resname SOL and name O" \
  --analysis-backend mdanalysis --r-max 1.0 --bin-width 0.002 \
  --output results/cn
```

径向命令支持 `--start`、`--stop`、`--stride`、`--analysis-backend` 和 `--figures false`。`stride` 从 `start` 开始按帧计数。进程内格式支持取决于内置 MDAnalysis，不支持 TNG。

提取 EDR series：

```bash
uv run mdhelper analyze energy \
  --energy-file ener.edr --terms '[Potential, Temperature]' \
  --output results/energy
```

## 项目与工具

```bash
uv run mdhelper project create \
  --path analysis-project --topology topol.tpr \
  --trajectory md.xtc --index index.ndx
uv run mdhelper project show --path analysis-project

uv run mdhelper config init
uv run mdhelper integrations list
uv run mdhelper integrations detect gromacs
uv run mdhelper templates list
```

向 `inspect` 或 `analyze` 传入 `--project analysis-project`，即可使用已校验的项目输入并提交结果。

Project 检查会根据 `.itp` 电荷数据提供角色建议。匹配、确认和选择规则见[选择与物种角色](SELECTIONS.zh-CN.md#物种角色)。

## GUI Workflow

Workflow 保存有序的分析类型序列。序列中的项目共用 GUI 已加载的输入，但各自保留独立的参数和绘图队列。

1. 打开 **Settings**，在 `config.toml` 中加入命名序列：

   ```toml
   [workflows]
   standard = ["rdf", "cumulative_rdf", "energy"]
   ```

2. 保存文件并重启 MDHelper，使更新后的配置生效。支持的标识和校验规则见[配置说明](CONFIGURATION.zh-CN.md#workflow)。
3. 在 **Load Input** 标签页选择 Workflow 共用的输入。如需在选择控件中使用 index group，先检查 index 文件。
4. 选择 **Tools > Run Workflow...**，再选择已命名的 Workflow。
5. 通过左侧项目列表或 **Back** 和 **Next** 逐项审查。径向项目可以输入一个 selection pair，也可以加入多个队列项。**Next** 会校验当前项目。
6. 在最后一个项目选择 **Run**。MDHelper 会再次校验全部项目，并按照 Workflow 顺序将所有启用的队列项提交到标准分析队列。

其他分析正在运行时不能打开 Workflow 面板。重复的分析标识表示相互独立的项目，可以使用不同的参数或绘图队列。

## 开发检查

测试和性能分析命令统一见[架构：开发检查](ARCHITECTURE.zh-CN.md#开发检查)，原生构建与发布验证见[打包](PACKAGING.zh-CN.md)。
