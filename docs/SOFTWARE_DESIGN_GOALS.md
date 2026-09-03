# MDHelper software design goals

[English](SOFTWARE_DESIGN_GOALS.md) | [Simplified Chinese](SOFTWARE_DESIGN_GOALS.zh-CN.md)

These constraints apply to MDHelper 0.1.0 changes. Version 0.1.0 does not preserve earlier
development APIs, schemas, or behavior. A contract change updates all producers, consumers,
schemas, tests, and documents without a migration branch.

## Priorities

1. Method correctness and reproducibility.
2. Data integrity and failure handling.
3. Explicit control and actionable errors.
4. Bounded resources and cancellation.
5. Equivalent behavior across interfaces.
6. Maintainability.
7. Presentation.

## Constraints

| ID | Constraint | Acceptance |
| --- | --- | --- |
| G1 | A released analysis includes a method, contracts, backend support, application use case, interfaces, persistence, export, tests, and documentation. | An end-to-end run loads from a project and exports a validated result. |
| G2 | Scientific formulas live in the analysis layer and versioned method documents. | Reference tests cover PBC, grids, normalization, and self exclusion; interfaces contain no formulas. |
| G3 | Dependencies follow [Architecture](ARCHITECTURE.md). | `tests/test_architecture.py` passes. |
| G4 | Selections, parameters, frame ranges, backends, and role decisions are explicit request data. | Validation and provenance account for each decision; no input-name special cases exist. |
| G5 | Suggestions expose evidence and never change source data or parameters. | Unavailable and low-confidence outcomes remain valid analysis results. |
| G6 | Results are versioned, strict, and self-describing. | Runtime parsers and JSON schemas reject unknown, missing, or inconsistent fields. |
| G7 | Results identify inputs, environment, selections, parameters, frames, and resolved backend. | Content changes and project relocation are detected by SHA-256. |
| G8 | Project persistence is failure-atomic. | Failed writes leave the prior project readable and do not publish partial results. |
| G9 | Work streams by frame or chunk and supports cancellation. | Memory does not scale with trajectory frame count; cancellation does not commit a result. |
| G10 | One backend owns one complete attempt. | Explicit backends do not fall back; automatic fallback does not mix components. |
| G11 | CLI, TUI, and GUI call the same application use cases. | Equivalent inputs create equivalent requests and results. |
| G12 | Plot state is separate from result data. | Preview and export use the same model; style changes do not alter result arrays. |
| G13 | External programs run through the integration boundary. | Commands use argv, `shell=False`, timeouts, cancellation, and run records. |
| G14 | Configuration and templates use validated contracts. | Resources load from wheels and frozen builds without a source checkout. |
| G15 | Errors expose a category and action without text parsing. | Interfaces distinguish input, method, cancellation, integration, and internal failures. |
| G16 | Extension work stays at declared boundaries. | New features use registries and protocols without copying an existing call chain. |

## Current decisions

| Topic | Decision |
| --- | --- |
| Entry point | No arguments select GUI when available, then TUI; explicit modes select GUI, TUI, or CLI. |
| Backends | MDAnalysis and GROMACS are complete pipelines; GROMACS is optional. |
| Selection | MDAnalysis uses NDX or static expressions; GROMACS uses NDX or native expressions. |
| Parameters | Requests contain radial limits, bin width, frame range, and backend. |
| Suggestions | Species roles and first-shell boundaries require confirmation and do not change calculations. |
| Project | A JSON manifest indexes hashed input and result files. |
| Jobs | One worker is the default; cancellation is cooperative. |
| Plotting | Residue-name and fixed colors are supported; plot state is persisted. |
| Statistics | Base methods do not report uncertainty. |
| Cache | Cache data is rebuildable; analysis results are not cached. |
| Artifacts | Each wheel, executable, and archive must not exceed 256 MB. |

## Release gates

- Versioned method documents match calculation code and validation evidence.
- PBC, changing boxes, overlapping selections, frame ranges, and invalid input have tests.
- Request, result, project, plot, and configuration schemas match runtime validation.
- Atomic writes, cancellation, process failure, and project corruption have tests.
- CLI stdout remains machine-readable; TUI and GUI remain responsive and headless-safe.
- Linux and Windows test suites, Ruff, mypy, and source ASCII checks pass.
- Wheel and frozen-build audits include declared resources and reject stale modules.
- Each portable archive passes startup and resource smoke tests on its target platform.

## Review questions

1. Which contract or use case changes?
2. Do formulas, units, PBC, selection, or frame sampling change?
3. Do all interfaces construct the same request semantics?
4. Are new defaults, suggestions, or fallbacks recorded in provenance?
5. Do runtime validation and schemas agree?
6. Are memory, progress, cancellation, and failure behavior bounded?
7. Can a failed write expose partial state?
8. Does each dependency remain in its owning package?
9. Are new resources included in release artifacts?
10. Do methods, validation, limitations, and user documents match the implementation?
