# MDHelper 0.1.0 architecture

[English](ARCHITECTURE.md) | [Simplified Chinese](ARCHITECTURE.zh-CN.md)

This document describes the current repository for engineers who modify, review, test, package,
or release MDHelper. Analysis behavior and deterministic engineering rules are centralized in
[Algorithm specification](ALGORITHM.md); released method definitions and evidence are under
[methods](methods/README.md) and [validation](validation/).

## 1. System boundary

MDHelper is a Python 3.12 molecular-dynamics analysis application. Version 0.1.0 provides RDF,
GROMACS-style cumulative RDF and EDR energy extraction. A native
reader supports GRO trajectories; MDAnalysis supports broader topology/trajectory combinations and
EDR files. Atom identity comes from a GROMACS NDX group or a static MDAnalysis selection expression.

The application has three presentation adapters:

- TUI: guided terminal interaction and the fallback when GUI startup is unavailable;
- CLI: non-interactive automation;
- GUI: the preferred argument-free interface when Qt and a display are available.

All three use the same application services and contracts. GROMACS is optional: an explicit
`gromacs` request is a native RDF, cumulative RDF, trajectory, or Energy backend.

## 2. Dependency direction

```text
CLI / TUI / GUI
        |
        v
ApplicationService facade
        |
        v
app use cases -----------------------> workflow
        |                                  |
        +--> analysis --> plugins          |
        +--> services --> backends         |
        +--> project                       |
        +--> io                            |
        +--> integrations --> runtime      |
        |                                  |
        +----------------------------------+
                         |
                         v
                        core
```

`core` is the innermost package and cannot import another MDHelper package. Presentation packages
cannot import each other or bypass `app` to call `analysis` or `backends`. Static checks in
`tests/test_architecture.py` enforce these boundaries, forbid presentation files outside their
packages, and keep compatibility shells out of the package root.

## 3. Package map

| Package | Responsibility |
| --- | --- |
| `bootstrap` | unified interface dispatch and portable configuration bootstrap |
| `core` | shared contracts, protocols, errors, units, and plotting models |
| `app` | use-case orchestration and the public facade used by all frontends |
| `analysis` | RDF, cumulative RDF, energy extraction, PBC, and shared numerical work |
| `plugins` | in-process analysis-runner registry |
| `services` | configuration, system inspection, selection, provenance, and templates |
| `backends` | native GRO, MDAnalysis, and GROMACS trajectory/selection adapters |
| `io` | NDX parsing and data/figure export |
| `project` | strict manifest, input identity, results, and atomic storage |
| `workflow` | task state, background execution, progress, and cancellation |
| `integrations` | domain adapters for optional external executables |
| `runtime` | subprocess, detection, environment, and logging infrastructure |
| `cli`, `tui`, `gui` | presentation-only adapters |
| `resources` | packaged read-only templates |

The `mdhelper/` root contains only `__init__.py`, `__main__.py`, and `version.py`.

## 4. Composition root

`bootstrap/portable.py` sends an argument-free `mdhelper` invocation to GUI when available and
falls back to TUI. Explicit `gui`, `tui`, and `cli` modes remain presentation-separated; other
arguments go to CLI. Every frozen distribution selects its colocated `config.toml` unless the user
explicitly selected another configuration. The Windows build contains one console-subsystem
launcher so PowerShell and other shells wait for terminal modes and keep their standard streams
connected. GUI startup creates an independent detached application process and then ends the
console launcher, allowing a temporary Windows Terminal host to close before the Qt main window
continues. Terminal modes keep their inherited console or allocate one when needed.

`app/facade.py` is the composition root. `ApplicationService` creates the context and exposes
analysis, inspection, project, integration, and template use cases. Readers and registries are injectable,
which lets tests exercise the application boundary without a real GUI or external executable.
`app/reports/` defines the shared readable result-report hierarchy consumed by both GUI and TUI.
`Report` owns common sections and technical metadata; RDF, CN, and energy subclasses own
their distinct result and configuration rows. Adapters only render a Report as HTML or terminal
text.

## 5. Core contracts

`core/analysis.py` defines `AnalysisRequest` and `AnalysisResult`. Every frontend
must build a request before an analysis runs; analysis code never reads presentation state.
Arrays are stored in result `data`, explanation in `diagnostics`, and reproduction information in
`provenance`. Schema-1 parsing is strict: missing fields, unknown fields, old identifiers, invalid
enums, and inconsistent arrays fail. Version 0.1.0 has no data-migration branch.

Internal radial data use nm, while plotting converts distance to angstrom without rewriting the
result. The stable cumulative RDF contract is:

- `analysis_type = "cumulative_rdf"`;
- request roles `reference` and `selection`;
- curve field `cumulative_number`;
- first-shell scalar diagnostic `coordination_number`.

`core/system.py` defines atoms, frames, frame ranges, boxes, and system summaries.
`core/trajectory.py` defines the narrow stream protocol consumed by analysis. `core/selection.py`
defines selection engines. `core/species.py` defines descriptive roles; roles cannot select atoms or
modify numerical parameters.

`core/plotting.py` builds GUI-independent plot series and panels. RDF and cumulative RDF share a
distance domain and may use left/right Y axes. The cumulative curve is `N(r)` and its Y label is
`Coordination number`. Energy terms form separate plot windows by default and may be assigned an
explicit shared group in one window. Each window renders one plot. Plot state stores the result ID,
selected result series, panel group, visibility,
legend, color, custom title, and strict primary/secondary limit fields. The GUI edits the title of
the plot containing the current visible series and synchronizes that title across its grouped
series; project restore and figure export consume the same state.

## 6. Application layer

Presentation calls flow through this sequence:

```text
presentation
  -> ApplicationService
  -> AnalysisUseCases.run(request)
  -> trajectory loader and selection service
  -> provenance builder
  -> AnalysisRegistry.get(analysis_type)
  -> analysis runner
  -> result validation
  -> caller-requested export or project commit
  -> presentation
```

The request exposes one Backend choice. The application records the resolved analysis backend and
trajectory adapter separately in provenance,
fingerprints inputs, records role decisions, and validates runner output. Every Integration command
that contributes to a result is attached as a run record with software identity, version,
executable, and arguments. Role warnings are diagnostic only. First-shell detection happens after
radial computation and does not become an input parameter.

## 7. Analysis implementations

`analysis/__init__.py` registers the built-in runners. `analysis/radial.py` performs one
shared half-width ordered-pair histogram accumulation, then resamples it onto the centered RDF
grid and edge-aligned cumulative grid. `rdf.py` publishes `g_r`; `cumulative_rdf.py` publishes
`cumulative_number`. `common.py` owns frame auditing, triclinic
minimum image, reliable-radius checks, bounded pair chunks, progress, and cancellation checks.

`gmx_rdf.py` is the explicit GROMACS RDF/CN runner. It preserves zero-based Python frame slicing,
invokes `gmx rdf` with `-cn` through Integrations, parses both XVG curves into the common result
contract, and retains the trajectory-conversion and RDF run records. Full and contiguous frame
ranges can read the original trajectory; strided ranges use the exact converted subset.

`energy.py` provides GROMACS and MDAnalysis EDR backends behind one result contract. The GROMACS
backend discovers the numbered menu and extracts the ordered queue through `gmx energy`, retaining
the Integration run in result provenance. The MDAnalysis backend reads ordered terms, time, values,
and units directly through `EDRReader`. Presentation code calls the shared application discovery
use case and never parses an EDR menu itself.

The implementation invariants and formulas are specified in [ALGORITHM.md](ALGORITHM.md). Released
method meaning and validation tolerance belong in the method and validation documents, not in
presentation code.

## 8. Services and backends

The system service summarizes atoms and proposes explainable species roles. For in-process
analyses, the selection service chooses NDX or a static expression engine and returns fixed ordered
indices plus a resolution record. GROMACS RDF/CN either quotes exact NDX group names or passes
GROMACS selection expressions to `gmx rdf`. Integrations own external-software configuration,
detection, status, and execution;
configuration, template discovery, and provenance remain separate services so the analysis layer
stays free of machine-specific executable handling.

`backends/trajectory.py` deterministically selects native GRO, MDAnalysis, or an explicitly requested
GROMACS conversion adapter. The native reader validates fixed atom identity and streams frames. The
MDAnalysis adapter converts third-party objects into core atoms, frames, boxes, and zero-based
indices; third-party objects do not cross the backend boundary. The GROMACS adapter invokes
`gmx trjconv` only through Integrations and then exposes the converted GRO through the same core port.
Explicit GROMACS RDF/CN does not use that conversion port for curve data: it passes the original
input paths to `gmx rdf`; a built-in reader supplies metadata and frame bounds only.

## 9. I/O and projects

NDX parsing lives under `io`, independently of CLI and GUI. Export accepts a validated
`AnalysisResult` and writes JSON/CSV data and PNG/SVG/PDF plots through atomic same-directory
replacement.
RDF exports `radius_nm,g_r`; cumulative RDF exports `radius_nm,cumulative_number`.

A project is rooted by `mdhelper-project.json` and owns `results/data`, `figures`, and
`cache`. Its manifest records schema/application version, content-addressed inputs, confirmed roles,
integration preferences and runs, strict plot state, and committed analysis entries. Every analysis
entry includes the path and hash of one complete result under `results/data`. Opening rejects old or
incomplete schema-1 data; it never rewrites an incompatible manifest into the current contract.

`cache` contains rebuildable performance data, currently MDAnalysis XDR frame-offset indexes rather
than analysis results. Offset files use a trajectory-path key, validate source size, nanosecond
modification time, and atom count, and are protected by a file lock and atomic replacement. Project
work uses the project cache; unbound inputs use a `cache` directory beside the trajectory. Removing
these files only forces an offset rescan and does not change analysis semantics.

Result commit validates request equality and provenance fingerprints, writes the result atomically,
hashes it, and then commits the manifest. Path containment and fingerprints are rechecked on load.
Relocation changes a path only when content identity is unchanged.

## 10. Workflow and external tools

`workflow` owns pending/running/completed/failed/cancelled state and progress messages. GUI polls
task state on the Qt thread; TUI and CLI can use the same use case synchronously. Cancellation is
cooperative at frame, hash-chunk, and process-poll points.

External tool adapters define executable candidates, identity checks, and capability detection.
Runtime code invokes an argument vector with `shell=False`, a restricted environment, timeout and
cancellation handling, and captured output. Every completed, failed, timed-out, or cancelled run is
auditable. Discovery only determines availability; request resolution chooses the analysis backend.

## 11. Presentation adapters

CLI parsing is isolated from command execution. `rdf` and `cn` use `--reference` and `--selection`;
`cn` constructs a `cumulative_rdf` request. Output remains script-oriented and errors map to stable
exit categories.

TUI stores an `AnalysisDraft`, reviews explicit choices, converts it to `AnalysisRequest`, and then
calls the facade. Its RDF + CN workflow creates two requests from one shared radial setup, exports
the raw results separately, and delegates the combined dual-axis figure to the shared plotting use
case. An unloaded workspace shows explicit project/workspace status and a Load-only menu; the
reduced main menu is rendered only after input or project loading. Integrations and Templates remain
separate Tools states. EDR selection invokes shared term discovery and presents an ordered marked
multi-select. It does not call CLI parsing or GUI widgets.

GUI separates widgets, application calls, and result formatting. `window.py` coordinates use cases;
`parameters.py` builds requests; `results.py` renders result text and core plot models; `species.py`
handles role confirmation. Both interactive frontends use one Backend selector. Energy remains
available through MDAnalysis; explicit GROMACS RDF/CN requires `rdf`, the general GROMACS
trajectory adapter requires `trjconv`, and GROMACS Energy requires `energy`. Backend selection is
independent from system inspection. New Project non-recursively discovers `.tpr`/`.gro` topology,
`.xtc`/`.trr`/`.gro` trajectory, and optional `.ndx` candidates. Background workers never mutate Qt
widgets.

Menu ordering is controlled by insertion order in `gui/menu.py`; analysis combo ordering is
controlled by `addItem` order in `gui/parameters.py`; TUI menu ordering is controlled by option tuple
order in `tui/controller.py`. Table sizing is controlled by `QHeaderView` resize modes and explicit
`resizeSection(column, pixels)` calls in the owning widget.

## 12. Testing and extension rules

Tests are layered:

- core/model tests validate strict data and plotting contracts;
- synthetic and reference tests validate formulas and PBC behavior;
- app/project/export tests validate orchestration and failure atomicity;
- CLI/TUI/GUI tests validate presentation adapters;
- architecture tests validate dependency direction and package layout;
- Linux and Windows runs exercise platform-specific dependency sets.

To add an analysis, define its request/result contract and method first, implement and register a
runner, expose it through app and each required presentation adapter, then add reference, schema,
export, persistence, and architecture tests. A new reader implements the core trajectory protocol
and is registered in the backend factory. A new frontend depends on `app` and `core` only.

Before committing a change, check strict schemas, layer direction, method invariants, resource
bounds, failure atomicity, all frontends, bilingual documentation, Linux tests, Windows tests, and
`tests/test_architecture.py`.
