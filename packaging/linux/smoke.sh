#!/usr/bin/env bash
set -euo pipefail

distribution=${1:?distribution directory is required}
application="$distribution/mdhelper"
export PYTHONWARNINGS=error

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
menu=$(printf 'q\n' | "$application")
if [[ "$menu" != *"Current workspace: not loaded"* ]]; then
    echo "Argument-free startup did not fall back to TUI." >&2
    exit 1
fi

config="$distribution/config.toml"
reported=$(env -u MDHELPER_CONFIG "$application" cli config path)
if [[ "$reported" != "$config" ]]; then
    echo "Colocated config mismatch: $reported" >&2
    exit 1
fi
env -u MDHELPER_CONFIG "$application" cli config check >/dev/null
"$application" cli integrations templates >/dev/null
