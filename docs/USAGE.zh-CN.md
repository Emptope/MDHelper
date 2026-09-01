# MDHelper 使用说明

[English](USAGE.md) | [简体中文](USAGE.zh-CN.md)

## 源码环境

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

## 检查输入

在选择分析组之前检查体系：

```bash
uv run mdhelper inspect \
  --topology md.gro \
  --trajectory md.xtc \
  --index index.ndx
```

## RDF

使用 NDX Group Name 计算 RDF：

```bash
uv run mdhelper analyze rdf \
  --topology md.gro \
  --trajectory md.xtc \
  --index index.ndx \
  --reference "<GROUP_NAME>" \
  --selection "<GROUP_NAME>" \
  --analysis-backend gromacs \
  --r-max 1.0 \
  --bin-width 0.002 \
  --output results/rdf
```

## 累积 RDF

使用 MDAnalysis 表达式计算累积 RDF：

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

径向分析命令还支持 `--start`、`--stop`、`--stride`、`--analysis-backend` 和
`--figures false`。`stride` 的单位是帧；`10` 表示从 `start` 开始每 10 帧取一帧。

## Energy

从 GROMACS energy 文件提取指定序列：

```bash
uv run mdhelper analyze energy \
  --energy-file ener.edr \
  --terms '[Potential, Temperature]' \
  --output results/energy
```

## 项目

创建并检查项目：

```bash
uv run mdhelper project create \
  --path analysis-project \
  --topology topol.tpr \
  --trajectory md.xtc \
  --index index.ndx

uv run mdhelper project show --path analysis-project
```

向 `inspect` 或 `analyze` 子命令传入 `--project analysis-project`，即可使用经过校验的项目
输入，并在分析完成后提交结果。

## Integrations 与 Templates

```bash
uv run mdhelper config init
uv run mdhelper integrations list
uv run mdhelper integrations detect gromacs
uv run mdhelper templates list
```

## 开发检查

```bash
uv run ruff check src tests
uv run mypy src
uv run pytest
```

使用 `uv run mdhelper --help` 或子命令的帮助查看全部参数。
