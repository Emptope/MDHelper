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

Project inspection recursively scans all subdirectories for `.itp` files. A matching
`[ moleculetype ]` name provides an advisory role from the sum of its `[ atoms ]` charges. Review
or change every suggestion before confirmation. When no matching `.itp` definition is found, select
the role manually. Only confirmed roles are saved; suggestion details remain in the current session.
When all species are matched, GUI inspection also warns if the inferred system net charge lies
outside the `1e-6 e` neutrality tolerance.

## GUI workflows

A workflow stores an ordered sequence of analysis types. It reuses the inputs loaded in the GUI,
while keeping separate parameters and plot series for every project in the sequence.

1. Open **Settings** and add a named sequence to `config.toml`:

   ```toml
   [workflows]
   standard = ["rdf", "cumulative_rdf", "energy"]
   ```

2. Save the file and restart MDHelper so the updated configuration is loaded. See
   [Configuration](CONFIGURATION.md#workflows) for the supported identifiers and validation rules.
3. In the **Load Input** tab, select the inputs shared by the workflow. Inspect an index file first
   when its groups should be available in the selection controls.
4. Choose **Tools > Run Workflow...**, then select the named workflow.
5. Review each project with the sidebar or **Back** and **Next**. For a radial project, enter one
   selection pair or add multiple configured series. **Next** validates the current project.
6. Select **Run** on the final project. MDHelper validates every project again and submits all
   enabled series to the standard analysis queue in workflow order.

The workflow dialog cannot open while another analysis is running. Repeated analysis identifiers
are separate projects and may use different parameters or series.

## Development checks

```bash
uv run ruff check src tests
uv run mypy src
uv run pytest
```
