# MDHelper usage

[English](USAGE.md) | [Simplified Chinese](USAGE.zh-CN.md)

## Setup

Source development requires Python 3.12 or newer and
[`uv`](https://docs.astral.sh/uv/):

```bash
uv sync --group dev
uv run mdhelper --version
```

Run `uv run mdhelper` for automatic GUI/TUI selection. Use `gui`, `tui`, or `cli` to select an
interface. Run `uv run mdhelper --help` for command options.

## Inspect and analyze

Inspect inputs before selecting groups:

```bash
uv run mdhelper inspect \
  --topology md.gro --trajectory md.xtc --index index.ndx
```

Run RDF with NDX group names:

```bash
uv run mdhelper analyze rdf \
  --topology md.gro --trajectory md.xtc --index index.ndx \
  --reference "<GROUP_NAME>" --selection "<GROUP_NAME>" \
  --analysis-backend gromacs --r-max 1.0 --bin-width 0.002 \
  --output results/rdf
```

Run cumulative RDF with MDAnalysis expressions:

```bash
uv run mdhelper analyze cumulative-rdf \
  --topology topol.tpr --trajectory md.xtc \
  --reference "resname LI" --selection "resname SOL and name O" \
  --analysis-backend mdanalysis --r-max 1.0 --bin-width 0.002 \
  --output results/cn
```

Radial commands accept `--start`, `--stop`, `--stride`, `--analysis-backend`, and
`--figures false`. `stride` counts frames relative to `start`.

Extract EDR series:

```bash
uv run mdhelper analyze energy \
  --energy-file ener.edr --terms '[Potential, Temperature]' \
  --output results/energy
```

## Projects and tools

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

Pass `--project analysis-project` to `inspect` or `analyze` to use verified project inputs and
commit the result.

## Development checks

```bash
uv run ruff check src tests
uv run mypy src
uv run pytest
```
