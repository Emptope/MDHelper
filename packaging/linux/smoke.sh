#!/usr/bin/env bash
set -euo pipefail

distribution=${1:?distribution directory is required}
variant=${2:-headless}
application="$distribution/mdhelper"
export PYTHONWARNINGS=error

if [[ "$variant" != headless && "$variant" != gui ]]; then
    echo "Unknown Linux package variant: $variant" >&2
    exit 1
fi

if [[ ! -x "$application" ]]; then
    echo "Missing packaged application: $application" >&2
    exit 1
fi

mapfile -t executables < <(find "$distribution" -maxdepth 1 -type f -perm -111)
if [[ ${#executables[@]} -ne 1 ]]; then
    echo "Expected one packaged executable, found ${#executables[@]}." >&2
    exit 1
fi

"$application" --version
"$application" tui --smoke-test
if ! printf '3\n' | env -u DISPLAY -u WAYLAND_DISPLAY -u QT_QPA_PLATFORM "$application" >/dev/null; then
    echo "Argument-free startup did not fall back to TUI." >&2
    exit 1
fi

if [[ "$variant" == gui ]]; then
    QT_QPA_PLATFORM=offscreen "$application" gui --smoke-test
elif QT_QPA_PLATFORM=offscreen "$application" gui --smoke-test; then
    echo "Headless package unexpectedly started the GUI." >&2
    exit 1
else
    status=$?
    if [[ $status -ne 6 ]]; then
        echo "Headless GUI startup returned $status instead of 6." >&2
        exit 1
    fi
fi

config="$distribution/config.toml"
reported=$(env -u MDHELPER_CONFIG "$application" cli config path)
if [[ "$reported" != "$config" ]]; then
    echo "Colocated config mismatch: $reported" >&2
    exit 1
fi
env -u MDHELPER_CONFIG "$application" cli config check >/dev/null
"$application" cli templates list >/dev/null
