# MDHelper configuration

[English](CONFIGURATION.md) | [Simplified Chinese](CONFIGURATION.zh-CN.md)

MDHelper uses a versioned, editable TOML user configuration. Supported external software uses a
common shape under `[integrations.<name>]`. Registered adapters supply candidate names,
environment paths, version parsing, and capability detection. The default registry contains
GROMACS and VMD.

By default, `config.toml` is stored next to the current executable or Python runtime:

```text
<executable directory>/config.toml
```

`MDHELPER_CONFIG` can point to a different file for automation and testing. Machine-specific executable paths belong in this user file, never in a portable project manifest.

Every platform archive contains `config.toml` next to its single executable. Every frozen
executable uses that colocated file automatically, so users can edit it directly and move the
whole directory together. A CLI `--settings` argument or an existing `MDHELPER_CONFIG` value
overrides the default location.

Diagnostic logs use the platform user-log directory. `MDHELPER_LOG` can select an explicit
file for support or automated testing. Logging is local and best-effort; a log-write failure
never replaces the original user-facing error.

## GUI appearance

The GUI starts in the operating system's current color scheme by default. Use **View →
Appearance** to select System, Light, or Dark. The choice is applied immediately and saved in
the shared configuration:

```toml
[gui]
theme = "system" # system, light, or dark
font_size = 11.0 # points, from 6 through 32
```

All three modes retain the same Qt platform-native control style, so widget geometry does not
change when switching appearance. System restores the platform palette and continues to react to
system color-scheme changes; Light and Dark apply explicit application-wide palettes on the same
controls.

## Backend

One complete Backend is selected per analysis request (`auto`, `native`, `mdanalysis`, or
`gromacs`) in the GUI, TUI, or CLI. It is intentionally not a machine-wide TOML setting: it fixes
the reader, selection language, frame handling, and computation for that request. The value is
visible in setup review and stored in the request. Auto considers Native only for GRO/GRO plus
NDX, then MDAnalysis, then an available GROMACS pipeline; expression mode resolves to MDAnalysis.
Energy considers MDAnalysis before available GROMACS. Explicit selections never fall back.
GROMACS RDF passes the original inputs directly to `gmx rdf`; cumulative RDF adds `-cn` for the
default full frame range. Energy uses `gmx energy`. A non-default frame range uses one
`gmx trjconv -fr` command to create an exact temporary XTC subset and keeps the original topology
for `gmx rdf`. Every non-default range first obtains the frame count with `gmx check`.

## Strict initial-version contracts

Version 0.1.0 is the initial contract. Project requests and plot state must use the current schema
exactly; unknown, missing, or retired development fields are rejected and are not migrated.

## Integration configuration and detection

Every integration accepts the same fields:

```toml
[integrations.gromacs]
enabled = true
path = ""
search_paths = []
use_environment = true
detect_timeout_seconds = 10.0
run_timeout_seconds = 3600.0
```

`path` is the preferred full executable path. Each `search_paths` item is another executable
candidate, not a directory to scan. `use_environment = false` disables adapter environment paths
but does not disable configured paths or `PATH`. Positive detection and run timeouts are in
seconds. A disabled integration has no automatic candidates, although an explicit per-run path is
still allowed.

Candidates are detected in this stable order and deduplicated by canonical path:

1. per-run `--path` override;
2. `[integrations.<name>].path`;
3. `[integrations.<name>].search_paths` in configured order;
4. adapter environment paths;
5. registered command names resolved on `PATH`;
6. adapter platform candidate paths.

For GROMACS, environment paths include the full path in `MDHELPER_GROMACS` and `gmx`/`gmx_mpi`
under `GMXBIN`; its command names are also resolved on `PATH`. VMD follows the same contract with
its own adapter-provided names and paths.

Each candidate must pass adapter identity/version and capability detection. `IntegrationStatus`
records availability, selected path, version, capabilities, source, error, and all detection
attempts. Detection does not select a trajectory or analysis backend. Execution uses an argument
vector with `shell=False`, a defined working directory, a restricted inherited environment,
timeout/cancellation handling, and an integration run record.

On Windows, **Tools > Integrations** is limited to configuration and detection. A successful
detection fills the configured executable field and presents status, version, source, and
capabilities as readable fields. Detect uses the current dialog draft, including an unsaved
configured executable. Saving replaces any cached detection status so the next use validates the
new configuration. The analysis backend selector does not show GROMACS until the user explicitly
runs this detection action in the current session or the saved configuration contains a non-empty
GROMACS executable path. Integration commands are invoked by analysis use cases or the explicit
CLI command instead of this configuration dialog.

Completed, non-zero, timed-out, and cancelled invocations record the resolved executable, detected
version, argument vector, working directory, relevant environment summary, exit code, captured
logs, elapsed time, status, and fingerprints of requested output files. Timeout and cancellation
return this record inside the actionable error details. Long-running commands stream captured
output into progress callbacks, and cancellation terminates the complete process group.

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
