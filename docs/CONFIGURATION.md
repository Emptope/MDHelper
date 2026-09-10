# MDHelper configuration

[English](CONFIGURATION.md) | [简体中文](CONFIGURATION.zh-CN.md)

MDHelper uses a schema-versioned TOML file.

Configuration resolution order is:

1. CLI `--settings`.
2. `MDHELPER_CONFIG`.
3. On macOS, `~/.config/mdhelper/config.toml` (both source and `.app` launches);
   otherwise, `config.toml` beside the executable or Python runtime.

Open **MDHelper > Settings…** on macOS (**⌘,**), or the existing **Settings** menu-bar entry elsewhere,
to edit the active file in your default TOML editor. A missing file is created automatically.
Run `mdhelper config path` to check its location. Existing configurations in
`~/Library/Application Support/MDHelper/` or beside Python are not moved automatically;
copy them to the new location if needed, or use `MDHELPER_CONFIG` to keep the old path.

## GUI

The GUI stores appearance in the shared configuration:

```toml
[gui]
theme = "system" # system, light, dark
font_size = 11.0 # 6 through 32 points
```

**View > Appearance** applies and saves the theme. `system` follows the operating-system color
scheme. Edit `font_size` in the configuration and restart to change the application font size.

The Workspace text editor uses the system fixed-width font at a minimum of 14pt, or the
application font size when larger, with 1.35x line spacing for readability. Spacing is display-only:
it does not change file content or undo history. Line numbers stay outside the document and are
never saved as file content. The footer shows the 1-based line and column, plus the selected character count.
Columns count Unicode code points, with tab stops every four columns; selected line breaks count
as one character. This position display is hidden for image and data-table previews.

Workspace detects text by content, without extension-specific exceptions. Text is displayed in
its original form rather than parsed into a table. Files larger than 1 MiB show a clearly labeled,
read-only preview of the first 1 MiB; saving that partial preview is disabled. Images retain their
image preview, and only binary data is passed to the scientific data readers.

**Export Text...** defaults to UTF-8 CSV (comma-separated); TXT (tab-delimited) remains available,
but TSV is not offered. EDR exports contain Frame, Time, and only the checked terms, including
units in the headers and all frames. Search filters do not change checked terms. At least one
term must be checked; export uses the selection at the time it is started.

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
GROMACS is optional, and supported versions can produce different external-backend results.

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
