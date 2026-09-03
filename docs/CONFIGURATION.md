# MDHelper configuration

[English](CONFIGURATION.md) | [Simplified Chinese](CONFIGURATION.zh-CN.md)

MDHelper uses a schema-versioned TOML file. It rejects unknown fields and invalid values.

Configuration resolution order is:

1. CLI `--settings`.
2. `MDHELPER_CONFIG`.
3. `config.toml` beside the executable or Python runtime.

Portable archives include the third path. Machine-specific executable paths belong in this file,
not in project manifests. `MDHELPER_LOG` overrides the platform user-log path. Logging failure does
not replace the original error.

## GUI

The GUI stores appearance in the shared configuration:

```toml
[gui]
theme = "system" # system, light, dark
font_size = 11.0 # 6 through 32 points
```

**View > Appearance** applies and saves these fields. `system` follows the operating-system color
scheme.

## Workflows

Named workflows contain an ordered list of analysis project identifiers:

```toml
[workflows]
radial = ["rdf", "cumulative_rdf"]
full = ["rdf", "cumulative_rdf", "energy"]
```

Supported identifiers are `rdf`, `cumulative_rdf`, and `energy`. A project may appear more than
once. **Tools > Run Workflow...** opens every project for review in configured order, then submits
the complete sequence through the standard analysis queue.

## Analysis backend

Each request selects `auto`, `mdanalysis`, or `gromacs`. This value is request data, not a global
setting. It fixes loading, selection syntax, frame handling, and calculation. Auto considers
MDAnalysis before an available GROMACS pipeline. Explicit selections do not fall back.

## Integrations

All integrations use this shape:

```toml
[integrations.gromacs]
enabled = true
path = ""
search_paths = []
use_environment = true
detect_timeout_seconds = 10.0
run_timeout_seconds = 3600.0
```

`path` and each `search_paths` item identify executable files. `use_environment = false` disables
adapter environment candidates but retains configured paths and `PATH`. A disabled integration has
no automatic candidates; a per-run path remains valid.

Candidates are deduplicated by canonical path and checked in this order:

1. Per-run path.
2. Configured `path`.
3. Configured `search_paths`.
4. Adapter environment paths.
5. Registered names on `PATH`.
6. Adapter platform paths.

GROMACS uses `MDHELPER_GROMACS`, candidates under `GMXBIN`, and `gmx` or `gmx_mpi` on `PATH`.
VMD uses the same contract with adapter-specific candidates.

Detection verifies identity, version, and capabilities. Execution uses argv, `shell=False`, a
working directory, a restricted environment, timeout and cancellation, and a run record. The
record contains the executable, version, argv, working directory, environment summary, exit code,
captured streams, duration, status, and output hashes.

On Windows, **Tools > Integrations** edits and detects integrations. The analysis selector exposes
GROMACS after detection in the current session or when the saved path is non-empty.

## Commands

```bash
mdhelper config path
mdhelper config init
mdhelper config check
mdhelper config show
mdhelper integrations list
mdhelper integrations detect gromacs
mdhelper integrations run gromacs -- --version
mdhelper templates list
```
