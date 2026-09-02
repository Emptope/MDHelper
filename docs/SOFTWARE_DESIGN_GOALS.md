# MDHelper 0.1.0 software design goals

[English](SOFTWARE_DESIGN_GOALS.md) | [Simplified Chinese](SOFTWARE_DESIGN_GOALS.zh-CN.md)

This document states the engineering properties that changes to MDHelper must preserve and how
they are accepted. [Architecture](ARCHITECTURE.md) describes how the system is assembled;
[Algorithm specification](ALGORITHM.md) describes how data are calculated.

Version 0.1.0 is the initial development version. It has no obligation to preserve an earlier API,
file format, or behavior. An incorrect early design is changed directly across implementation,
contracts, schemas, documentation, and tests; compatibility and migration branches are not added.

## 1. Product scope and priorities

The current product goal is a reproducible vertical slice from trajectory or EDR input and explicit
atom or energy-term selection through analysis, interpretation, export, and project persistence in
CLI, TUI, and GUI. The released analyses are RDF, cumulative RDF, and energy
extraction. Native, MDAnalysis, and optional GROMACS are complete, non-mixing pipelines. Each owns
its reader, selection path, frame handling, and analysis implementation. The requested and resolved
backend are always recorded.

When goals compete, use this order:

1. method correctness and reproducibility;
2. data integrity and failure safety;
3. explicit user control and actionable errors;
4. bounded resources and cancellability;
5. consistent behavior across frontends;
6. maintainability and extension cost;
7. visual convenience.

## 2. G1: complete vertical slices

Every released analysis must have a method definition, request/result contract, supporting backend adapters,
application use case, CLI/TUI/GUI exposure where applicable, persistence, export, reference tests,
and user documentation. A menu item or algorithm module alone is not a completed feature.

Acceptance requires an end-to-end run through the application boundary and round-trip project
loading/export. Incomplete capabilities must not be advertised.

## 3. G2: one source per method

PBC, pair definition, grids, normalization, cumulative counts, and shell diagnostics live in the
analysis layer and its versioned method documents. Presentation adapters only
collect parameters and format validated results.

Acceptance requires synthetic/reference tests and a repository search confirming that formulas
are not duplicated in CLI, TUI, GUI, or export code.

## 4. G3: stable core and one-way dependencies

Shared contracts and protocols live in `core`. Dependencies point inward as specified in
[ARCHITECTURE.md](ARCHITECTURE.md). Presentation packages enter through `ApplicationService` and
cannot import each other or analysis implementations.

`tests/test_architecture.py` is a required release gate. Business modules at the package root,
cross-presentation imports, or presentation code placed outside its package fail the gate.

## 5. G4: explicit selection, parameters, and sampling

Reference/selection identity, index file, radial limits, bin width, cutoffs, grouping mode, frame
range, analysis backend, and role decisions are explicit request data. No filename, residue name, sample,
test, software name, or prior output may secretly alter them.

Acceptance requires reviewable setup in interactive frontends, complete CLI arguments, strict
request validation, and provenance of every decision.

## 6. G5: explainable suggestions do not change facts

Species roles and first-shell boundaries are suggestions or diagnostics with method, evidence,
confidence, reason, and confirmation state. They cannot replace atom selections, choose cutoffs,
or change arrays.

Unavailable or ambiguous evidence remains unavailable. Acceptance tests must show that accepting,
overriding, or omitting role metadata leaves numerical results unchanged for identical requests.

## 7. G6: strict, self-describing results

Requests, results, projects, plot state, and external-run records are versioned, JSON-safe, and
strictly parsed. Radial and Energy requests use disjoint fields. Units, method version, schema
version, request, warnings, diagnostics, and provenance have distinct fields; unimplemented
uncertainty and constant completion fields are not serialized.

Version 0.1.0 accepts only its current field names. Unknown, missing, obsolete, non-finite, or
inconsistent data fail at the boundary; they are not migrated. Every project result entry is a
compact index containing an ID, analysis type, commit time, and content fingerprint.

## 8. G7: complete provenance

An analysis result records application/runtime/library versions, platform, requested and resolved
complete backend, input paths and SHA-256 values, selection-resolution identity, role decisions,
and parameter decisions. `auto` is not sufficient as a resolved backend record.

Acceptance verifies that changed input content cannot be silently committed, loaded, or relocated.

## 9. G8: failure-atomic persistence

Configuration, exports, manifests, and results use same-directory temporary files and atomic
replacement. A result becomes visible in a project only after both its file and manifest entry are
valid. A failed manifest commit removes the newly created unindexed result.

Tests inject write and replacement failures and confirm that the last committed project remains
loadable, with no false manifest entry.

## 10. G9: bounded resources and cancellation

Trajectory frames stream, pair matrices are chunked, and file hashing is chunked. MDAnalysis XDR
frame offsets are stored as rebuildable, locked, atomically replaced entries in a dedicated cache
directory instead of sidecars beside the trajectory, and are invalidated by source metadata.
Background jobs have explicit state and cooperative cancellation. No analysis may materialize
every frame or an unbounded
`N_reference x N_selection` matrix.

Acceptance covers configured pair bounds, multi-frame streaming, progress, cancellation, timeout,
and deterministic cleanup.

## 11. G10: deterministic complete backends

Analysis backend selection is explicit and recorded. One registered adapter owns the reader,
selection path, frame handling, and computation for every analysis it supports. Backend adapters
convert third-party objects to core contracts before shared result assembly. Unit conversion, box
conversion, atom identity, frame-range behavior, and computation ownership are tested.

`auto` evaluates declared complete strategies in priority order. A source-loading failure can try
the next complete strategy, but components from separate backends are never combined in one
attempt. Explicit selection never falls back.

## 12. G11: equivalent frontends with clear ownership

CLI, TUI, and GUI construct the same request and receive the same result. They may differ in
interaction style but not in analysis defaults or meaning. User-facing analysis names, roles,
selection labels, and units come from shared vocabulary where practical.

The GUI remains responsive by keeping analysis off the Qt thread. TUI does not reuse CLI parsing;
GUI does not reuse TUI controllers. Each adapter has presentation-specific tests.

## 13. G12: plotting is separate from data

Plots derive from immutable results through `core.plotting`. Changing titles, colors, labels,
visible series, or axis limits never rewrites result arrays. Compatible RDF and cumulative RDF curves
can share a distance axis while retaining independent Y scales.

The cumulative curve is `N(r)` and its Y-axis label is `Coordination number`. Plot state stores
custom titles, explicit primary and secondary bounds, and strict color identifiers.

## 14. G13: isolated and auditable external programs

External programs use registered adapters, verified identity/capabilities, argument vectors,
`shell=False`, explicit working directories, restricted environments, timeouts, cancellation, and
structured run records. Discovery determines availability; the explicit or automatic request rule
selects a backend and records the resolution.

Acceptance covers missing executables, wrong identity, missing capability, non-zero exit, timeout,
cancellation, output capture, and fingerprints.

## 15. G14: valid configuration and portable environments

User configuration has a documented TOML schema and machine-local executable paths. Portable mode
changes only configuration location. Saved configuration is validated before replacement. Each
project input stores one portable relative path when possible, otherwise one absolute path, plus
content identity.

Templates are deterministic, non-empty, ASCII, and rejected on key collision. Configuration or
template errors are actionable rather than silently defaulted.

## 16. G15: actionable errors; logs are not contracts

Domain errors carry a summary, recovery action, category, and structured details where useful.
Frontends format the same error appropriately. Logs aid diagnosis but are not parsed for behavior
and never replace the original user-facing failure.

Tests assert error categories or stable contract data, not incidental trace text.

## 17. G16: controlled extension cost

Adding an analysis, backend, frontend, or external tool follows the extension rules in
[ARCHITECTURE.md](ARCHITECTURE.md). Registries and protocols are narrow; speculative abstraction is
avoided. New code must extract repository-wide invariants before implementation and remain generic.

An extension is accepted only when contracts, architecture checks, reference tests, all affected
frontends, exports, persistence, and bilingual documentation are complete.

## 18. Key decisions and non-goals

Current key decisions include fixed atom identity, explicit selection roles, nm/ps internal units,
GROMACS-compatible cumulative RDF semantics, strict initial-version schemas, content-addressed
inputs/results, rebuildable XDR offset caching, one application facade, and a flat GUI without
small helper text. Analysis results are not cached.

Version 0.1.0 does not promise dynamic selections, center-of-mass RDF, slab/orientational RDF,
automatic statistical uncertainty, automatic cutoff selection, chemical perception, arbitrary
plugin discovery, remote execution, or an external program as a hidden analysis backend. See
[Known limitations](KNOWN_LIMITATIONS.md) for observable-specific boundaries.

## 19. Release gates

Method gates:

- formulas and endpoints match method documents;
- synthetic/reference and bounded MD regression tests pass;
- units, selection identities, diagnostics, and provenance are complete;
- deterministic base results are not presented as uncertainty estimates.

Software gates:

- Ruff and mypy pass;
- the complete Linux suite passes;
- `tests/test_architecture.py` passes;
- project failure-atomicity and strict-schema tests pass;
- local documentation links resolve.

Platform and distribution gates:

- the Linux x86_64 standalone archive starts both TUI and CLI without Python or Qt installed;
- the complete Windows `.venv-windows` suite passes;
- one public launcher keeps TUI, CLI, and GUI adapters separate and starts each mode;
- argument-free startup prefers GUI and falls back to TUI when GUI is unavailable;
- every wheel, executable, and portable archive is at most 256 MB;
- wheel and portable artifacts contain current schemas and bilingual documentation;
- an artifact is considered validated only after its target-platform smoke test succeeds.

## 20. Review checklist

- Is the change an implemented vertical slice rather than an advertised stub?
- Is every method rule defined once and independently validated?
- Are inputs explicit and outcomes free of filename/species/test special cases?
- Are contracts strict and free of compatibility or migration branches?
- Are provenance, units, diagnostics, and failure semantics preserved?
- Are memory, progress, cancellation, atomic writes, and path containment preserved?
- Do CLI, TUI, and GUI remain semantically equivalent and layer-correct?
- Are English and Chinese documentation both updated?
- Do Ruff, mypy, Linux, architecture, and Windows gates pass?
