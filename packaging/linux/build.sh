#!/usr/bin/env bash
set -euo pipefail

python=${PYTHON:-python}
max_size_mb=${MAX_ARTIFACT_SIZE_MB:-256}
project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
release_output="$project_root/dist/linux"
work_root="$project_root/build/pyinstaller-linux"
smoke_request="$project_root/packaging/smoke/request.json"
version=$($python -c 'import mdhelper; print(mdhelper.__version__)')
"$python" "$project_root/packaging/clean_build.py" --root "$project_root"
stage=$(mktemp -d)
export MPLCONFIGDIR="$work_root/matplotlib"

cleanup() {
    rm -rf -- "$stage"
}
trap cleanup EXIT

case "$release_output" in
    "$project_root"/dist/*) ;;
    *) echo "Invalid output directory: $release_output" >&2; exit 1 ;;
esac
rm -rf -- "$release_output"
mkdir -p "$release_output" "$MPLCONFIGDIR"

if ! "$python" -c 'import PySide6' >/dev/null 2>&1; then
    echo "Linux GUI build requires the locked gui extra: uv sync --frozen --extra gui --group dev" >&2
    exit 1
fi

build_variant() {
    local variant=$1
    local gui=$2
    local name=$3
    local audit_platform=$4
    local application_output="$stage/application-$variant"
    local work="$work_root/$variant"
    local archive="$release_output/$name.tar.gz"
    local root="$stage/$name"
    local verified="$stage/verified-$variant"
    local notices=(
        "$project_root/packaging/generate_notices.py"
        --output "$root/licenses/THIRD_PARTY_NOTICES.json"
    )

    if [[ "$gui" == 1 ]]; then
        MDHELPER_LINUX_GUI_BUILD=1 "$python" -m PyInstaller \
            --clean \
            --noconfirm \
            --distpath "$application_output" \
            --workpath "$work" \
            "$project_root/packaging/linux/mdhelper.spec"
        notices+=(--extra gui)
    else
        env -u MDHELPER_LINUX_GUI_BUILD "$python" -m PyInstaller \
            --clean \
            --noconfirm \
            --distpath "$application_output" \
            --workpath "$work" \
            "$project_root/packaging/linux/mdhelper.spec"
    fi

    "$python" "$project_root/packaging/frozen_audit.py" \
        --application "$application_output/mdhelper" \
        --platform "$audit_platform" \
        --max-size-mb "$max_size_mb"

    mkdir -p "$root"
    cp "$application_output/mdhelper" "$root/mdhelper"
    cp "$project_root/LICENSE" "$root/LICENSE"
    cp "$project_root/README.md" "$root/README.md"
    cp "$project_root/README.zh-CN.md" "$root/README.zh-CN.md"
    cp "$project_root/config.example.toml" "$root/config.example.toml"
    cp "$project_root/config.example.toml" "$root/config.toml"
    cp -R "$project_root/docs" "$root/docs"
    cp -R "$project_root/schemas" "$root/schemas"
    "$python" "${notices[@]}"

    tar -C "$stage" -czf "$archive" "$name"
    "$python" "$project_root/packaging/frozen_audit.py" \
        --artifact "$archive" \
        --platform "$audit_platform" \
        --max-size-mb "$max_size_mb"
    mkdir -p "$verified"
    tar -C "$verified" -xzf "$archive"
    "$project_root/packaging/linux/smoke.sh" \
        "$verified/$name" \
        "$variant" \
        "$smoke_request"
    printf 'Linux %s archive: %s\n' "$variant" "$archive"
}

build_variant \
    headless \
    0 \
    "MDHelper-$version-Linux-x86_64" \
    linux
build_variant \
    gui \
    1 \
    "MDHelper-$version-Linux-x86_64-GUI" \
    linux-gui
