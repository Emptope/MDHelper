# MDHelper 0.1.0 architecture

[English](ARCHITECTURE.md) | [Simplified Chinese](ARCHITECTURE.zh-CN.md)

This document describes the current repository for engineers who modify, review, test, package,
or release MDHelper. Analysis behavior and deterministic engineering rules are centralized in
[Algorithm specification](ALGORITHM.md); released method definitions and evidence are under
[methods](methods/README.md) and [validation](validation/).

## 1. System boundary

MDHelper is a Python 3.12 molecular-dynamics analysis application. Version 0.1.0 provides RDF,
GROMACS-style cumulative RDF and EDR energy extraction. Native, MDAnalysis, and GROMACS are
complete analysis pipelines. Each pipeline owns its input reader, selection rules, frame handling,
and numerical or external analysis implementation.

The application has three presentation adapters:

- TUI: guided terminal interaction and the fallback when GUI startup is unavailable;
- CLI: non-interactive automation;
- GUI: the preferred argument-free interface when Qt and a display are available.

All three interfaces use the same application services and contracts. GROMACS is optional; an
explicit `gromacs` request uses GROMACS input processing and GROMACS analysis commands throughout.

## 2. Dependency direction

```text
CLI / TUI / GUI
        |
        v
ApplicationService facade
        |
        v
app use cases --------------------------> jobs
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
| `jobs` | job state, background execution, progress, and cancellation |
| `workflow` | reserved boundary for future user-authored workflows |
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
text. `app/exports.py` plans readable result directories and plot destinations for both interactive
frontends; `AnalysisUseCases` executes those plans through the I/O boundary.

## 5. Core contracts

`core/analysis.py` defines the shared `AnalysisRequest` boundary plus disjoint
`RadialRequest` and `EnergyRequest` records. Every frontend must build the matching request before
an analysis runs; analysis code never reads presentation state. Serialized requests contain only
fields used by that analysis family.
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
Interactive project figure saving writes one PNG/SVG/PDF set per plot model directly under
`figures`, using canonical names allocated against both the current batch and existing image sets.
Models with multiple series of one analysis type use `rdf`, `cn`, or `energy`; mixed RDF/CN models
use `rdf-cn`. Name collisions append numeric suffixes starting at `-2`. Standalone radial and Energy
models retain their readable Pair or term name. GUI and TUI result bundles rebuild one standalone
model per result item inside its analysis directory. A TUI radial task batch additionally saves its
shared plot model at the export root through the same flat figure plan used by Save Plot. The plot
dialog derives its initial client size from the Figure canvas and layout margins, so opening it does
not change the aspect ratio later consumed by Save Plot or Export.

## 6. Application layer

Presentation calls flow through this sequence:

```text
presentation
  -> ApplicationService
  -> AnalysisUseCases.run(request)
  -> complete backend selection
  -> backend-owned trajectory loader and selection path
  -> provenance builder
  -> backend adapter
  -> result validation
  -> caller-requested export or project commit
  -> presentation
```

The request exposes one `analysis_backend` choice. `AnalysisRegistry` stores each complete backend
once; the backend declares all supported analysis types and its Auto priority. Auto considers
Native for GRO/GRO plus NDX, then MDAnalysis, then GROMACS when the required capabilities are
available. Source-loading failure may advance to the next complete candidate, but one attempt never
mixes backend components. Provenance records requested and resolved backend identities rather than
a separate reader backend. In-process backends fingerprint inputs; direct external backends start
their native command without a pre-run hash pass. The application records role decisions and
validates adapter output. Every Integration command that contributes to a result is attached as a
run record with software identity, version, executable, exact formatted command, and arguments. The
execution layer writes the same command to the diagnostic log. GROMACS progress is derived from its
captured native output and never substitutes the command for an output line. Role warnings are
diagnostic only. First-shell detection happens after radial computation and does not become an
input parameter.

## 7. Analysis implementations

`analysis/__init__.py` registers exactly one adapter for each built-in complete pipeline:
`NativeBackend`, `MDAnalysisBackend`, and `GromacsBackend`. The registry is keyed by backend name,
not by the Cartesian product of backend and analysis type. `analysis/radial.py` performs one
shared half-width ordered-pair histogram accumulation, using periodic cell pruning for large local
pair searches, then resamples it onto the centered RDF grid and edge-aligned cumulative grid.
`rdf.py` publishes `g_r`; `cumulative_rdf.py` publishes `cumulative_number`. `common.py` owns frame
auditing, triclinic minimum image, reliable-radius checks, bounded pair chunks, progress, and
cancellation checks.

`gromacs.py` is the complete GROMACS adapter. Its radial path preserves zero-based Python frame
slicing and invokes `gmx rdf` through Integrations. RDF requests use only `-o`; cumulative RDF adds
`-cn` and parses both XVG curves. Both retain every metadata-inspection, trajectory-conversion, and
RDF run record. The default full range reads the original trajectory directly; non-default ranges
obtain the frame count with `gmx check` and use one exact converted subset.

`mdanalysis.py` owns MDAnalysis radial and Energy dispatch, while `native.py` owns Native radial
dispatch. `energy.py` contains private Energy implementations shared by the complete adapters.
GROMACS discovers and extracts terms through `gmx energy`; MDAnalysis reads terms, time, values,
and units through `EDRReader`. Presentation code calls the application discovery use case and never
parses an EDR menu itself.

The implementation invariants and formulas are specified in [ALGORITHM.md](ALGORITHM.md). Released
method meaning and validation tolerance belong in the method and validation documents, not in
presentation code.

## 8. Services and backends

The system service summarizes atoms and proposes explainable species roles. Native requires NDX
groups. MDAnalysis uses NDX groups when supplied and otherwise uses static MDAnalysis expressions.
GROMACS RDF/CN quotes exact NDX group names or passes GROMACS selection expressions to `gmx rdf`.
Integrations own external-software configuration,
detection, status, and execution;
configuration, template discovery, and provenance remain separate services so the analysis layer
stays free of machine-specific executable handling.

For analysis, `backends/trajectory.py` receives the already resolved backend name; it does not make
a second policy choice. The MDHelper reader validates fixed atom identity and streams frames. The
MDAnalysis adapter converts third-party objects into core atoms, frames, boxes, and zero-based
indices; third-party objects do not cross the backend boundary. The GROMACS analysis adapter
bypasses the trajectory port: default full-range RDF/CN passes the original inputs directly to
`gmx rdf`, while a non-default range obtains its frame count through `gmx check` and uses one
GROMACS-generated exact subset. The metadata check validates an explicit stop without a full
coordinate expansion. Every external command is invoked through Integrations.

## 9. I/O and projects

NDX parsing lives under `io`, independently of CLI and GUI. Export accepts a validated
`AnalysisResult` and writes JSON/CSV data and PNG/SVG/PDF plots through atomic
same-directory replacement. RDF exports `radius_nm,g_r`; cumulative RDF exports
`radius_nm,cumulative_number`. Integration stdout/stderr bodies are external `.out`/`.err` files;
persisted JSON retains stream fingerprints but not stream bodies or paths.

A project is rooted by `mdhelper-project.json` and owns `results/data`, `results/runs`, `figures`,
and `cache`. Its manifest records schema/application version, content-addressed inputs, confirmed
roles, strict plot state, and committed analysis entries. Result integration metadata stays in the
result JSON, with deterministic fingerprinted `.out`/`.err` siblings under `results/data`.
Standalone integration records and streams live under `results/runs`. Every analysis
entry includes an ID, analysis type, commit time, and hash. Its result path is derived as
`results/data/<analysis_id>.json`; request and method metadata live only in that complete result.
Opening rejects old or incomplete schema-1 data; it never rewrites an incompatible manifest into
the current contract. Each input record stores one relative path when portable, or one absolute
path when a relative path cannot be represented, plus its hash.

`cache` contains rebuildable working data rather than canonical analysis results. This includes
MDAnalysis XDR frame-offset indexes and retained GROMACS command work directories with native
outputs and exact frame subsets. Project work uses the project cache; unbound GROMACS analysis uses
a process-lifetime system directory. Removing cache files only forces regeneration and does not
change analysis semantics.

Result commit validates request equality, input paths, and any recorded provenance fingerprints,
externalizes integration streams, writes the result atomically, hashes it, and then commits the
compact manifest index. Result loading verifies and hydrates referenced logs. Derived result and log
paths are checked for containment, and fingerprints are rechecked on load.
Relocation changes a path only when content identity is unchanged.

## 10. Jobs and external tools

`jobs` owns pending/running/completed/failed/cancelled state and retained raw progress messages. GUI
polls job state on the Qt thread; TUI and CLI can use the same use case synchronously. Cancellation is
cooperative at frame, hash-chunk, and process-poll points. External-process polling streams output
to the active stage progress callback and terminates the complete process group on cancellation.
The `workflow` package is reserved for future user-authored orchestration and currently has no
implementation.

External tool adapters define executable candidates, identity checks, and capability detection.
Runtime code invokes an argument vector with `shell=False`, a restricted environment, timeout and
cancellation handling, and captured output. Every completed, failed, timed-out, or cancelled run is
auditable. Discovery only determines availability; request resolution chooses the analysis backend.
Interactive backend selectors expose GROMACS only after an explicit Integrations detection action
in the current session or a saved executable path; internal Auto discovery does not expose it.

## 11. Presentation adapters

CLI grammar is composed from command-specific modules and parsed into native `jsonargparse`
namespaces. Execution receives only the selected namespace. `analyze rdf` and
`analyze cumulative-rdf` use `--reference` and `--selection`; the latter constructs a
`cumulative_rdf` request. Structured roles, terms, and capability lists accept JSON or YAML values,
and `--args-file` loads a complete invocation. Output remains script-oriented and errors map to
stable exit categories.

TUI stores an `AnalysisDraft`, converts explicit choices to `AnalysisRequest`, and calls the facade
immediately when Run is selected. RDF and CN drafts add the initial selection to ordered queues of
typed selection and radial-parameter snapshots. The RDF + CN workflow owns a separate mixed queue
and creates exactly one request per explicit RDF or CN task. It exports each result and standalone
plot to a readable directory and writes a shared dual-axis model as `rdf-cn` when both types are
present. Save Plot uses the same model in the flat project-figure layout, and both paths use the
GUI's application plans. The initial Load menu can open a project, enter the main menu without
inputs, or quit. Open project matches the GUI flow: existing projects open directly, while ordinary
directories use discovered input candidates to create a project. Analysis-dependent actions retain
their input guards, while independent main-menu actions remain available without loaded inputs.
System and project is one direct main-menu action for input loading, inspection, project binding,
and session reset. Its shared load action treats a directory as a project and a file as topology,
then requests the remaining trajectory inputs. Species roles remains a separate direct action.
Integrations and Templates remain separate Tools states. EDR selection
invokes shared term discovery and presents an ordered marked multi-select. It does not call CLI
parsing or GUI widgets. `tui/controller.py` owns only top-level navigation and error handling;
focused controllers under `tui/controllers/` own workspace, analysis setup, execution, results, and
tools workflows.

GUI separates widgets, application calls, and result formatting. `gui/window.py` coordinates use
cases and composes four focused subpackages: `components` owns reusable widgets, `pages` owns the
workspace views, `dialogs` owns floating windows, and `controllers` owns session and background-job
coordination. `components/parameters.py` builds requests; `pages/results.py` renders result text and
core plot models; `components/species.py` handles role confirmation. Both interactive frontends
expose Backend under Analysis, not
Load. Energy remains available through MDAnalysis; GROMACS RDF/CN requires `rdf`, frame subsets
additionally require `trjconv` and `check`, and GROMACS Energy requires
`energy`. Backend selection is
independent from system inspection. New
Project non-recursively discovers `.tpr`/`.gro` topology,
`.xtc`/`.trr`/`.gro` trajectory, and optional `.ndx` candidates. Background workers never mutate Qt
widgets.

The Analysis action bar keeps its Progress title and Run/Cancel controls on one row in that order, with progress and its
Details action below. Details opens `dialogs/log.py` as a non-modal raw-message window, so menus and
the main workspace remain interactive. The viewer follows new messages while it is at the bottom,
preserves position when the user scrolls up, and confirms clipboard copies without blocking.
Consecutive identical progress text is retained once because repeated callback values update
progress state rather than representing distinct log events.

Menu ordering is controlled by insertion order in `gui/menu.py`; analysis combo ordering is
controlled by `addItem` order in `gui/components/parameters.py`; TUI menu ordering is controlled by
option tuple order in each owning controller. Table sizing is controlled by `QHeaderView` resize modes and explicit
`resizeSection(column, pixels)` calls in the owning widget.

## 12. Testing and extension rules

Tests are layered:

- core/model tests validate strict data and plotting contracts;
- synthetic and reference tests validate formulas and PBC behavior;
- app/project/export tests validate orchestration and failure atomicity;
- CLI/TUI/GUI tests validate presentation adapters;
- architecture tests validate dependency direction and package layout;
- Linux and Windows runs exercise platform-specific dependency sets.

To add an analysis, define its request/result contract and method first, implement it in each
supporting complete backend adapter, expose it through app and each required presentation adapter,
then add reference, schema, export, persistence, and architecture tests. Adding an analysis does
not create new registry entries. A new backend implements one complete adapter, declares all
supported analyses and Auto policy, and is registered once. A new frontend depends on `app` and
`core` only.

Before committing a change, check strict schemas, layer direction, method invariants, resource
bounds, failure atomicity, all frontends, bilingual documentation, Linux tests, Windows tests, and
`tests/test_architecture.py`.
