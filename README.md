# MDHelper

[English](README.md) | [Simplified Chinese](README.zh-CN.md)

> **A local data post-processing and visualization tool for molecular dynamics (MD) simulations**

MDHelper is a local data post-processing application designed for molecular dynamics simulations. It aims to simplify tedious analysis workflows, integrate multiple toolchains, and provide fast, reproducible data analysis, plotting, and export capabilities.

> [!NOTE]
> MDHelper is currently under rapid **0.1.0** development.

---

## Highlights

- **Two Analysis Pipelines**
  - **MDAnalysis**: Integrates the MDAnalysis ecosystem to read and process widely used trajectory formats.
  - **GROMACS**: Directly invokes a local `gmx` or `gmx_mpi` executable for input parsing and analysis.
- **Periodic Boundary Handling**: Full support for orthogonal and triclinic periodic boundary conditions (PBC).
- **One-Click Multi-Format Export**: Generates complete analysis JSON, structured CSV data, and publication-ready PNG, SVG, and PDF vector/raster figures in one click.
- **Integrations**: Completes tasks by invoking molecular simulation software already installed locally.

---

## Quick Start

| Mode | Command | Primary use | Supported platforms |
| :--- | :--- | :--- | :--- |
| **GUI** | `mdhelper` or `mdhelper gui` | Visual project management, interactive analysis, and real-time plotting | Windows / Linux |
| **TUI** | `mdhelper tui` | Guided terminal interaction for servers without a graphical environment | Windows / Linux |
| **CLI** | `mdhelper <command>` or `mdhelper cli <command>` | Command-line automation and batch processing | Windows / Linux |

### Running and Launching

- **Automatic Interface Fallback**: When `mdhelper` is run directly, it first checks for Qt and a display environment and starts the GUI when they are available; otherwise, it falls back smoothly to the TUI.
- **Ready to Use**: Linux and Windows release packages contain a single executable and a colocated `config.toml` file, with no administrator privileges required.
- **Source Development Requirements**: Building from source requires Python 3.12+ and the [`uv`](https://docs.astral.sh/uv/) package manager.

For detailed instructions, see [Usage](docs/USAGE.md) and [Packaging and Release Validation](docs/PACKAGING.md).

---

## Project Management and Data Export

When an analysis is run in a specified working directory, MDHelper automatically creates the `mdhelper-project.json` project configuration file and the corresponding data management directories:

```text
working-directory/
|-- mdhelper-project.json   # Project state and configuration
|-- results/                # Structured data files (JSON/CSV)
|-- figures/                # Automatically generated figures (PNG/SVG/PDF)
`-- cache/                  # Analysis cache
```

## Integrations

MDHelper can automatically detect and integrate third-party molecular simulation tools installed in the system environment. It currently supports:

- **GROMACS**
- **VMD**

For detailed configuration instructions, see [Configuration](docs/CONFIGURATION.md).

## Documentation Guide

> [!INFO]
> The project documentation is generated with assistance from gpt-5.6-sol and is under continuous maintenance and improvement.

- [Usage](docs/USAGE.md)
- [Configuration](docs/CONFIGURATION.md)
- [Selection Rules](docs/SELECTIONS.md)
- [Known Limitations](docs/KNOWN_LIMITATIONS.md)
- [Software Design Goals](docs/SOFTWARE_DESIGN_GOALS.md)
- [Software Architecture](docs/ARCHITECTURE.md)
- [Algorithm Details](docs/ALGORITHM.md)
- [Species Roles](docs/SPECIES.md)
- [Packaging](docs/PACKAGING.md)

## License

MDHelper is open source under the GNU General Public License version 2, with the SPDX identifier GPL-2.0. Third-party dependencies and external example data included in the project remain under their respective open source licenses.
