# MDHelper

[English](README.md) | [简体中文](README.zh-CN.md)

MDHelper 0.1.0 is a local, reproducible post-processing application for GROMACS molecular
dynamics data. It provides radial distribution function (RDF), GROMACS-style cumulative RDF
(shown as Cumulative Coordination Number, CN), and EDR energy
extraction through a guided terminal interface, an automation-ready CLI, and a Windows desktop
GUI.

> MDHelper is currently 0.1.0 alpha.

## Highlights

- One analysis implementation shared by the TUI, CLI, and GUI;
- streaming analysis of large trajectories with bounded pair-distance memory;
- MDHelper GRO Reader support for single- and multi-frame GRO, MDAnalysis-backed TPR/GRO and
  XTC/TRR support,
  and optional GROMACS-native trajectory, RDF/CN, and Energy backends;
- exact GROMACS NDX groups or explicit static MDAnalysis selections;
- orthorhombic and triclinic periodic boundary conditions;
- portable, fingerprint-verified projects with consolidated result data, analysis history, and
  plot state;
- complete JSON metadata, CSV data, and PNG/SVG/PDF figure export;
- a shared Integrations registry for controlled GROMACS and VMD detection, status, capabilities,
  and execution.

## Interfaces

| Interface | Command | Intended use | Supported release platform |
| --- | --- | --- | --- |
| TUI | `mdhelper tui` | Guided interactive analysis | Linux and Windows |
| CLI | `mdhelper <command>` or `mdhelper cli <command>` | Scripts and automation | Linux and Windows |
| GUI | `mdhelper` or `mdhelper gui` | Desktop projects, analysis, and plots | Windows; optional on Linux |

Calling `mdhelper` without arguments opens the GUI when Qt and a display are available, then
falls back to the numbered TUI when the GUI is unavailable. Explicit `gui`, `tui`, and `cli`
modes select an interface; other arguments are routed to the CLI. The TUI uses `0` to return from
nested menus and shows one review before an analysis begins. Before a workspace is loaded, it shows
the current project/workspace status and only the Load menu. Once loaded, its main menu contains
Analysis, Results, Workspace, and Tools; Tools keeps Integrations, Templates, and Configuration as
separate entries. Without an open project, the default export folder is
`results/<analysis-type>` beside the selected trajectory; project workspaces use
`<project>/exports/<analysis-type>`.

## Requirements and setup

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

Release packages are classified by platform under `dist/linux` and `dist/windows`, and both are
portable archives. The Linux x86_64 package contains one standalone `mdhelper` executable. It
bundles the CLI and TUI without Python, Qt, or installation requirements. Extract the archive,
then run `./mdhelper`, `./mdhelper tui`, or `./mdhelper cli --help`. Source development on Linux
has no Qt dependency; the optional GUI extra remains available only for development and testing.

The Windows x64 package is a ZIP with one `mdhelper.exe`. Extract it and keep the executable with
`config.toml`. It requires neither installation nor
administrator access. Every executable and release archive is rejected when it exceeds 256 MB. See
[Packaging and release validation](docs/PACKAGING.md) for build and validation details.

## Quick start

Inspect a system before selecting groups:

```bash
uv run mdhelper inspect \
  --topology topol.tpr \
  --trajectory md.xtc \
  --index index.ndx
```

Compute an RDF with exact NDX group names:

```bash
uv run mdhelper rdf \
  --topology topol.tpr \
  --trajectory md.xtc \
  --index index.ndx \
  --reference "Cations" \
  --selection "Solvent oxygen" \
  --backend gromacs \
  --r-max 1.0 \
  --bin-width 0.002 \
  --output results/rdf
```

Compute a cumulative RDF curve with MDAnalysis expressions:

```bash
uv run mdhelper cn \
  --topology topol.tpr \
  --trajectory md.xtc \
  --reference "resname LI" \
  --selection "resname SOL and name O" \
  --r-max 1.0 \
  --bin-width 0.002 \
  --output results/cn
```

Extract selected series from a GROMACS energy file and plot the standardized result:

```bash
uv run mdhelper energy \
  --energy-file ener.edr \
  --term Potential \
  --term Temperature \
  --output results/energy
```

In the GUI and TUI, selecting or changing an EDR file automatically discovers the complete term
menu through the selected Backend. `auto` reads the menu with MDAnalysis first and falls back to a
detected `gmx energy` only when MDAnalysis cannot read the file and that capability is available.
Add terms from the available list to the ordered analysis queue; no comma-separated term entry is
required.

All trajectory analysis commands also accept `--start`, `--stop`, `--stride`, `--backend`, and
`--no-figures`.

## Analyses

| Analysis | Result | Main explicit parameters |
| --- | --- | --- |
| RDF | Radius and `g(r)`, with an explainable first-shell diagnostic when available | Reference, selection, `r_max`, bin width, frames |
| Cumulative RDF (UI: Cumulative CN) | Radius and `N(r)` | Reference, selection, `r_max`, bin width, frames |
| Energy | Time and one standardized series per selected EDR term | EDR file, terms, backend |

The versioned method definitions and their validation evidence are published under
[docs/methods](docs/methods/README.md) and [docs/validation](docs/validation/).

## Inputs and selections

The MDHelper GRO Reader accepts single- or multi-frame `.gro` files. MDAnalysis supports `.tpr` or
`.gro` topology with `.xtc` or `.trr` trajectories. The optional `gromacs` trajectory
backend runs `gmx trjconv` through Integrations, converts to a standard multi-frame GRO file, and
then reuses the MDHelper GRO Reader. Format compatibility can depend on the installed MDAnalysis or
GROMACS version; in particular, a newer TPR may require a compatible GRO topology snapshot.
Explicit GROMACS RDF/CN bypasses that conversion adapter: `gmx rdf` reads the original topology
and trajectory directly. For a strided frame range, `gmx trjconv -fr` materializes the exact
zero-based frame indices as a temporary XTC while `gmx rdf` keeps the original topology.

GROMACS maps a structure/topology and an XTC trajectory by atom index. The XTC supplies the
ordered coordinates, atom count, step, time, and box; atom and residue metadata come from the
structure/topology. GROMACS normally checks only the atom count for this combination, so equal
counts cannot prove equal atom ordering. MDHelper follows this rule and never infers a pairing
from names such as `em`, `npt`, or `md`. Select a structure snapshot from the same system with
unchanged atom ordering. When a matching TPR is available, `gmx check -f trajectory.xtc -s1
topology.tpr` can additionally detect some ordering problems through inconsistent bond lengths.
See the official GROMACS documentation for [selection input
semantics](https://manual.gromacs.org/current/onlinehelp/selections.html), the [XTC
format](https://manual.gromacs.org/current/reference-manual/file-formats.html#xtc), and [`gmx
check`](https://manual.gromacs.org/current/onlinehelp/gmx-check.html).

GROMACS `.ndx` groups are the preferred selection source. When `--index` is present, every
selection argument is an exact, case-sensitive group name. Without an index file, explicit
GROMACS RDF/CN uses GROMACS selection expressions; the built-in trajectory analyses use static
MDAnalysis atom-selection expressions.

Selections are resolved once to fixed atom identities before frames are streamed. Coordinate-
dependent expressions such as `around`, `sphzone`, and `prop` are therefore rejected. See
[Atom and group selection](docs/SELECTIONS.md) for the supported syntax and validation rules.

## Projects and exports

A project keeps input fingerprints, confirmed species roles, completed results, integration run
records, and plot state together. Each complete result is stored and fingerprinted once under
`results/data/`:

```text
analysis-project/
  mdhelper-project.json
  results/
    data/
      <analysis-id>.json
  figures/
  cache/
```

Create and inspect a project from the CLI:

```bash
uv run mdhelper project create \
  --path analysis-project \
  --topology topol.tpr \
  --trajectory md.xtc \
  --index index.ndx

uv run mdhelper project show --path analysis-project
```

The project path must be new or empty. Pass `--project analysis-project` to `inspect`, `rdf`,
`cn`, or `energy` to reuse its verified inputs where applicable and commit the
completed result. Energy commits add the fingerprinted EDR file as the `energy` input. Projects
can be moved; MDHelper reconnects inputs only when their SHA-256 fingerprints still match.

In the Windows GUI, **File > New Project** discovers direct `.tpr`/`.gro` topology,
`.xtc`/`.trr`/`.gro` trajectory, and optional `.ndx` files in a selected directory. A sole
index candidate is selected automatically; multiple
candidates remain an explicit choice. Changing the selected topology, trajectory, or index file
reloads detected species and index groups without a separate inspection action. System inspection
uses the automatic built-in reader policy and is independent of the Backend selected for analysis;
changing the Backend alone does not reload the system. The first valid analysis
materializes an in-place project beside the trajectory. **File > Open Project** opens an explicit
`mdhelper-project.json` and verifies its inputs before restoring roles, results, and plot state.

Direct analysis exports contain a complete `result.json`, analysis-specific CSV files, and, by
default, PNG, SVG, and PDF figures. PNG files use 300 DPI; SVG and PDF remain vector output.
Numeric JSON and CSV values use stable 15-significant-digit formatting.

The GUI can compare multiple compatible results, combine RDF and CN on a shared distance axis
with separate Y axes, edit legends and colors, set explicit axis limits, save plot compositions,
and restore saved project results. Each selected GROMACS energy term uses a separate plot by
default, with one plot per window. Select energy rows in **Plot series** and use **Combine** to draw
them on shared axes in one window; **Separate** restores individual plot windows. These groups are
marked as `Combined` in the Plot column and preserved in project plot state and figure
exports.

The TUI analysis menu also provides **RDF + CN Combined Plot**. It reuses one radial setup for both
analyses, keeps their raw exports separate, and writes one combined PNG/SVG/PDF figure set.

## Method and reproducibility conventions

- Stored distances use nm and stored time uses ps; radial plot axes display angstroms converted
  from the stored nm values.
- RDF and cumulative RDF base results are deterministic over the explicitly selected
  frames; energy results preserve the explicitly selected EDR series.
- Version 0.1.0 schemas are strict initial contracts; retired development fields are rejected,
  not migrated.
- Base results do not estimate equilibration, autocorrelation, convergence, uncertainty, or
  standard error.
- Species-role suggestions are explainable metadata and always require confirmation. They never
  change selections, cutoffs, or numerical algorithms.
- First-shell detection is a post-analysis diagnostic. It never changes a curve.
- Requests, results, input files, backend decisions, software versions, selections, and frame
  audits are recorded for provenance.

Read [Known limitations](docs/KNOWN_LIMITATIONS.md) before interpreting production results.

## Integrations

The registry currently supports GROMACS and VMD. GROMACS is required when its explicit trajectory,
RDF/CN, or Energy backend, or controlled integration execution, is requested. MDAnalysis reads EDR
files directly without a GROMACS executable:

```bash
uv run mdhelper config init
uv run mdhelper integrations list
uv run mdhelper integrations detect gromacs
uv run mdhelper integrations templates
```

The shared Backend selector offers GROMACS only when a compatible executable is detected. Explicit
GROMACS RDF/CN requires `rdf`; the general GROMACS trajectory adapter requires `trjconv`, and
explicit GROMACS Energy requires `energy`. Energy
remains available through `auto` or MDAnalysis without GROMACS. Missing capabilities do not trigger
system inspection.

Detection uses this stable precedence: a per-run `--path`, `[integrations.<name>].path`, configured
`search_paths`, adapter environment paths, `PATH`, then platform candidate paths. For GROMACS the
environment sources include `MDHELPER_GROMACS` and `GMXBIN`. Status records availability, selected
path, version, capabilities, source, and all detection attempts. `auto` deterministically chooses
native for GRO pairs, MDAnalysis for other supported trajectories and EDR files, and falls back to
GROMACS Energy only when MDAnalysis EDR support is unavailable and `gmx energy` is available.
The Windows GUI configures and detects software under **Tools > Integrations**. A successful
detection fills the configured executable field and shows readable version, source, and capability
fields. Command execution belongs to analysis workflows or the explicit CLI command, not this
configuration dialog. Bundled text resources remain under **Tools > Templates**.

See [Configuration](docs/CONFIGURATION.md) for configuration locations, colocated behavior,
environment overrides, and integration-run provenance.

## Development and validation

Run the source quality checks with:

```bash
uv run ruff check src tests
uv run mypy src
uv run pytest
```

Useful design and implementation references:

- [Software design goals](docs/SOFTWARE_DESIGN_GOALS.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Algorithm details](docs/ALGORITHM.md)
- [Selection contract](docs/SELECTIONS.md)
- [Species roles](docs/SPECIES.md)
- [Packaging](docs/PACKAGING.md)

## License

MDHelper is distributed under the [GNU General Public License version 2](LICENSE), identified by
the SPDX expression `GPL-2.0`. Third-party dependencies and excluded simulation inputs remain
under their respective licenses.
