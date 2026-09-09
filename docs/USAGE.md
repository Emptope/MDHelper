# MDHelper usage

[English](USAGE.md) | [简体中文](USAGE.zh-CN.md)

## Setup

Source development requires Python 3.12 or newer and
[`uv`](https://docs.astral.sh/uv/):

```bash
uv sync --group dev
uv run mdhelper --version
```

Run `uv run mdhelper` for automatic GUI/TUI selection. Use `gui`, `tui`, or `cli` to select an
interface. Run `uv run mdhelper --help` for command options.

## Workspace files

Open a folder to browse independently of analysis inputs. File names appear above the content;
size, modification time, and format or read status appear below it.

- Binary tables load additional rows when you scroll. Only visited rows are cached on disk, with a
  bounded GUI page cache. The scrollbar covers loaded rows and grows as more data arrives; there is
  no frame selector or manual next-page button.
- XTC/TRR stream without an up-front frame-index scan. EDR uses a read-only memory map and parses
  requested frames rather than allocating every energy series. Other parsers may need format
  metadata or a complete first frame before displaying data; opening does not export all rows.
- UTF-8 text up to 1 MiB remains editable. Larger text is a read-only table of character offsets and
  text blocks. Double-click a cell to inspect the block. Saving partial content is disabled.
- Images are identified by content, including PNG, JPEG, GIF, BMP, TIFF, and WebP. The first image is
  decoded in the background only when visible, fitted to the viewport, and displayed with its
  original dimensions. Resize requests are coalesced; pixel buffers are released when leaving the
  page. Display decoding is limited to 2048 pixels per dimension. Decoders that cannot downsample
  before materializing more than 32 MiPixels report a memory-limit error rather than loading the
  unbounded original. This is not arbitrary-region decoding for all compressed image formats.

Cancel, file switching, and leaving Workspace stop pending loads and discard stale results. Existing
small-text edits still require save/discard confirmation before changing files.

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
In-process format support follows the bundled MDAnalysis version; TNG is unsupported.

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

Project inspection offers advisory roles from `.itp` charge data. See
[Selections and species roles](SELECTIONS.md#species-roles) for matching, confirmation, and
selection rules.

## GUI workflows

A workflow stores an ordered sequence of analysis types. It reuses the inputs loaded in the GUI,
while keeping separate parameters and a plot queue for every project in the sequence.

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
   selection pair or add multiple queue items. **Next** validates the current project.
6. Select **Run** on the final project. MDHelper validates every project again and submits all
   enabled queue items to the standard analysis queue in workflow order.

The workflow dialog cannot open while another analysis is running. Repeated analysis identifiers
are separate projects and may use different parameters or plot queues.

## Development checks

```bash
uv sync --frozen --extra gui --group dev
uv run prek run --all-files
uv audit --frozen
uv run --extra gui pytest -q -n 4 --dist worksteal \
  --cov=mdhelper --cov-report=term-missing:skip-covered
uv run zizmor .github
```

On Linux or WSL, install the separate profiling group and record a representative energy run:

```bash
uv sync --frozen --group dev --group profile
mkdir -p build/profiles
uv run --group profile memray run --native \
  -o build/profiles/energy.bin -m mdhelper analyze energy \
  --energy-file examples/LiFSI_DME_OPLS_0.8_small/md.edr \
  --terms '[Potential, Total Energy]' \
  --output build/profiles/result --figures false
uv run --group profile memray flamegraph \
  -o build/profiles/energy.html build/profiles/energy.bin
```

Run the Qt test suite without xdist workers on Windows:

```powershell
uv run --extra gui pytest -q `
  --cov=mdhelper --cov-report=term-missing:skip-covered
```
