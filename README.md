<h1 align="center">MDHelper</h1>

<p align="center">
  <img src="src/mdhelper/resources/icons/mdhelper.png" alt="MDHelper icon" width="128">
</p>

<p align="center">
  <a href="README.md">English</a> |
  <a href="README.zh-CN.md">简体中文</a>
</p>

> **A local data post-processing and visualization tool for molecular dynamics (MD) simulations**

MDHelper is a local data post-processing application designed for molecular dynamics simulations. It aims to simplify tedious analysis workflows, integrate multiple toolchains, and provide fast, reproducible data analysis, plotting, and export capabilities.

> [!NOTE]
> MDHelper is currently under rapid development.

---

## Highlights

- **Two Analysis Pipelines**
  - **MDAnalysis**: Integrates the MDAnalysis ecosystem to read and process widely used trajectory formats.
  - **GROMACS**: Directly invokes a local `gmx` or `gmx_mpi` executable for input parsing and analysis.
- **Periodic Boundary Handling**: Full support for orthogonal and triclinic periodic boundary conditions (PBC).
- **Workflow Design**: Supports reusable workflows defined in configuration files for batch processing and automated analysis.
- **One-Click Multi-Format Export**: Generates complete analysis JSON, structured CSV data, and publication-ready PNG, SVG, and PDF vector/raster figures in one click.
- **Integrations**: Completes tasks by invoking molecular simulation software already installed locally.

---

## Quick Start

| Mode | Command | Primary use | Supported platforms |
| :--- | :--- | :--- | :--- |
| **GUI** | `mdhelper` or `mdhelper gui` | Visual project management, interactive analysis, and real-time plotting | Windows / Linux / macOS arm64 |
| **TUI** | `mdhelper tui` | Guided terminal interaction for servers without a graphical environment | Windows / Linux / macOS arm64 |
| **CLI** | `mdhelper <command>` or `mdhelper cli <command>` | Command-line automation and batch processing | Windows / Linux / macOS arm64 |

### Running and Launching

- **Automatic Interface Fallback**: When `mdhelper` is run directly, it first checks for Qt and a display environment and starts the GUI when they are available; otherwise, it falls back smoothly to the TUI.
- **Ready to Use**: Release packages include colocated `config.toml` settings and require no administrator privileges. Windows bundles all dependencies in `mdhelper.exe` and provides a small `mdhelper.com` terminal entry for CLI/TUI, without an exposed library directory.
- **macOS arm64**: GUI, TUI, and CLI are supported on Apple Silicon. Open the DMG and drag `MDHelper.app` to Applications; source and wheel installations also include desktop dependencies. See [macOS packaging](docs/PACKAGING.md#macos-arm64) for commands and signing details.
- **Source Development Requirements**: Building from source requires Python 3.12+ and the [`uv`](https://docs.astral.sh/uv/) package manager.

### macOS First Launch

Releases are ad-hoc signed, not notarized. If Gatekeeper blocks a trusted download, follow [macOS installation and signature verification](docs/PACKAGING.md#macos-arm64).

For detailed instructions, see [Usage](docs/USAGE.md) and [Packaging and Release Validation](docs/PACKAGING.md).

---

## Project Management and Data Export

Analyses committed to a project are indexed by `mdhelper-project.json`, with results, figures, and rebuildable cache stored below the project directory. See [Projects and tools](docs/USAGE.md#projects-and-tools) for commands and [storage layout](docs/ARCHITECTURE.md#storage-and-jobs) for details.

## Workflow Design

Workflows are stored in `config.toml` as named, ordered sequences of analysis types. Projects in a workflow retain separate parameters and plot queues. After review, MDHelper submits the queue items to the standard analysis queue in order for repeatable analysis and batch processing.

For configuration and operation details, see [Configuration](docs/CONFIGURATION.md#workflows) and [Usage](docs/USAGE.md#gui-workflows).

## Integrations

MDHelper can automatically detect and integrate third-party molecular simulation tools installed in the system environment. It currently supports:

- **GROMACS**
- **VMD**

For detailed configuration instructions, see [Configuration](docs/CONFIGURATION.md).

## Documentation Guide

- [Usage](docs/USAGE.md)
- [Configuration](docs/CONFIGURATION.md)
- [Selections and Species Roles](docs/SELECTIONS.md)
- [Versioned Methods and Validation](docs/methods/README.md)
- [Algorithm Details](docs/ALGORITHM.md)
- [Software Architecture](docs/ARCHITECTURE.md)
- [Packaging](docs/PACKAGING.md)

## License

MDHelper is open source under the GNU General Public License version 2.
