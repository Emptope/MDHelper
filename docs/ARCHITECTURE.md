# MDHelper architecture

[English](ARCHITECTURE.md) | [简体中文](ARCHITECTURE.zh-CN.md)

## Package ownership

| Package | Responsibility |
| --- | --- |
| `bootstrap` | Unified CLI/TUI/GUI dispatch and portable configuration |
| `cli`, `tui`, `gui` | Input and presentation; call application features, not backends |
| `app` | Use-case orchestration, export plans, and reports |
| `jobs` | Progress, execution state, and cooperative cancellation |
| `core` | Domain contracts, errors, units, and plot models; no adapter dependencies |
| `analysis`, `backends` | Complete analysis pipelines, input loading, and selection |
| `services` | Configuration, inspection, provenance, and templates |
| `integrations`, `runtime` | External tools, filtered environments, process lifecycle, logging |
| `project`, `io` | Manifests, fingerprints, storage, parsing, and exports |

Only bootstrap composes presentation adapters. Qt belongs in `gui`; its state models remain usable without Qt. Analysis code must not depend on presentation or plotting. Process objects stay behind integrations and runtime. Avoid cyclic imports and reverse orchestration dependencies.

## Analysis flow

```text
request -> validation -> backend resolution -> input loading and static selection
        -> provenance -> execution -> result validation -> export or project commit
```

`app/facade.py` is the composition root. Each registry entry in `analysis/pipeline/` owns a complete backend attempt. Automatic fallback never mixes loading from one backend with calculation from another; explicit backend selection does not fall back.

`core/analysis/` defines schema-1 requests and results. `RadialRequest` covers RDF and cumulative RDF; `EnergyRequest` covers EDR series. Results own their request, arrays, units, diagnostics, provenance, and method version. Preview and export share `core/plotting/` models.

## Storage and jobs

```text
project/
|-- mdhelper-project.json
|-- results/
|   |-- data/
|   `-- runs/
|-- figures/
`-- cache/
```

The manifest indexes inputs, confirmed roles, results, and plot state. Full result JSON owns data and provenance. Paths must remain inside the project; loading verifies identities, hashes, and schemas. Writes use same-directory temporary files and atomic replacement. Failed manifest commits remove newly written unindexed results. Cache data is rebuildable.

Jobs move from pending to running, then completed, failed, or cancelled. Cancellation is checked at frame boundaries, hash chunks, and process polls. GUI workers report changes to the Qt thread; external commands use argument vectors, timeouts, captured streams, and process-group termination.

## Development checks

```bash
uv sync --frozen --extra gui --group dev
uv run prek run --all-files
uv run pytest -q --cov=mdhelper
```

Linux may add `-n 4 --dist worksteal`; macOS and Windows run Qt tests serially. Tests use offscreen Qt by default; `QT_QPA_PLATFORM=cocoa` enables native macOS checks. Keep behavioral regressions and representative boundary cases, rather than exhaustive style/font products or assertions about third-party painting and build-command text. Native package smoke tests belong to Quality CI. The coverage gate remains 80%.

For memory profiling on Linux/macOS, install `--group profile` and run a representative command under `uv run --group profile memray run --native -m mdhelper`.

See [algorithms](ALGORITHM.md), [configuration](CONFIGURATION.md), and [packaging](PACKAGING.md) for their respective contracts; [usage](USAGE.md) covers user workflows.
