# MDHelper 使用说明

[English](USAGE.md) | [简体中文](USAGE.zh-CN.md)

## 环境

源码开发需要 Python 3.12 或更高版本及
[`uv`](https://docs.astral.sh/uv/)：

```bash
uv sync --group dev
uv run mdhelper --version
```

`uv run mdhelper` 自动选择 GUI 或 TUI。使用 `gui`、`tui` 或 `cli` 指定界面。使用
`uv run mdhelper --help` 查看命令参数。

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

径向命令支持 `--start`、`--stop`、`--stride`、`--analysis-backend` 和 `--figures false`。
`stride` 从 `start` 开始按帧计数。

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

向 `inspect` 或 `analyze` 传入 `--project analysis-project`，即可使用已校验的项目输入并提交
结果。

## 开发检查

```bash
uv run ruff check src tests
uv run mypy src
uv run pytest
```
