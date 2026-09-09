#!/usr/bin/env bash
set -euo pipefail

distribution=${1:?distribution directory is required}
platform=${2:?target platform is required}
request=${3:?analysis request is required}
python=${PYTHON:-python}
project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
check_script="$project_root/packaging/smoke_check.py"
export PYTHONWARNINGS=error

case "$platform" in
    linux|linux-gui|macos) ;;
    *) echo "Unknown POSIX package platform: $platform" >&2; exit 1 ;;
esac
application=$(
    "$python" "$check_script" distribution \
        --root "$distribution" \
        --platform "$platform"
)
smoke_root=$(mktemp -d)
cleanup() {
    rm -rf -- "$smoke_root"
}
trap cleanup EXIT

"$application" --version
"$application" tui --smoke-test
if [[ "$platform" != macos ]] && ! env -u DISPLAY -u WAYLAND_DISPLAY -u QT_QPA_PLATFORM \
    "$application" </dev/null >/dev/null; then
    echo "Argument-free startup did not fall back to TUI." >&2
    exit 1
fi

if [[ "$platform" != linux ]]; then
    QT_QPA_PLATFORM=offscreen "$application" gui --smoke-test
    if [[ "$platform" == macos ]]; then
        QT_QPA_PLATFORM=cocoa "$application" gui --smoke-test
    fi
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
if [[ "$platform" == macos ]]; then
    config="$HOME/Library/Application Support/MDHelper/config.toml"
    env -u MDHELPER_CONFIG "$application" cli config init
fi
config_report="$smoke_root/config.json"
env -u MDHELPER_CONFIG "$application" cli config check >"$config_report"
"$python" "$check_script" config \
    --report "$config_report" \
    --expected-path "$config"
"$application" cli templates list >/dev/null

analysis_output="$smoke_root/analysis"
analysis_report="$smoke_root/analysis.json"
(
    cd "$project_root"
    "$application" cli analyze request \
        --request "$request" \
        --output "$analysis_output"
) >"$analysis_report"
"$python" "$check_script" analysis \
    --output "$analysis_output" \
    --report "$analysis_report"
