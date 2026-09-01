# MDHelper usage

[English](USAGE.md) | [Simplified Chinese](USAGE.zh-CN.md)

## Source setup

Source development requires Python 3.12 or newer and
[`uv`](https://docs.astral.sh/uv/):

```bash
uv sync --group dev
uv run mdhelper --version
```

Start an interface from the source tree:

```bash
uv run mdhelper
uv run mdhelper --help
uv run mdhelper gui
uv run mdhelper tui
```

## Inspect inputs

Inspect a system before selecting groups:

```bash
uv run mdhelper inspect \
  --topology md.gro \
  --trajectory md.xtc \
  --index index.ndx
```

## RDF

Compute an RDF with exact NDX group names:

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

## Cumulative RDF

Compute a cumulative RDF with MDAnalysis expressions:

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

Radial analysis commands also accept `--start`, `--stop`, `--stride`, `--analysis-backend`, and
`--figures false`. `stride` is measured in frames; `10` selects every tenth frame relative to
`start`.

## Energy

Extract selected EDR series:

```bash
uv run mdhelper analyze energy \
  --energy-file ener.edr \
  --terms '[Potential, Temperature]' \
  --output results/energy
```

## Projects

Create and inspect a project:

```bash
uv run mdhelper project create \
  --path analysis-project \
  --topology topol.tpr \
  --trajectory md.xtc \
  --index index.ndx

uv run mdhelper project show --path analysis-project
```

Pass `--project analysis-project` to `inspect` or an `analyze` subcommand to use verified project
inputs and commit a completed result.

## Integrations and templates

```bash
uv run mdhelper config init
uv run mdhelper integrations list
uv run mdhelper integrations detect gromacs
uv run mdhelper templates list
```

## Development checks

```bash
uv run ruff check src tests
uv run mypy src
uv run pytest
```

Use `uv run mdhelper --help` or the help for a subcommand to see all available parameters.
