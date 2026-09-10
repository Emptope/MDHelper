#!/usr/bin/env bash
set -euo pipefail

platform=${1:?target platform is required}
python=${PYTHON:-python}
case "$platform:$(uname -s):$(uname -m)" in
    linux:Linux:x86_64) label=Linux-x86_64; system=linux; machine=x86_64 ;;
    macos:Darwin:arm64) label=macOS-arm64; system=darwin; machine=arm64 ;;
    *) echo "Unsupported native build host for $platform." >&2; exit 1 ;;
esac
"$python" -c 'import platform, sys; assert (sys.platform, platform.machine()) == tuple(sys.argv[1:])' \
    "$system" "$machine"
max_size_mb=${MAX_ARTIFACT_SIZE_MB:-256}
project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
release_output="$project_root/dist/$platform"
work_root="$project_root/build/pyinstaller-$platform"
smoke_request=${SMOKE_REQUEST:-}
if [[ -n "$smoke_request" && "$smoke_request" != /* ]]; then
    smoke_request="$project_root/$smoke_request"
fi
version=$("$python" "$project_root/packaging/check_release.py" --root "$project_root")
stage=$(mktemp -d)
build_status=1
export MPLCONFIGDIR="$work_root/matplotlib"

cleanup() {
    local status=$1
    # Some shells report status zero after expansion errors; require explicit completion.
    if [[ "$status" == 0 ]]; then
        status=$build_status
    fi
    rm -rf -- "$stage"
    exit "$status"
}
trap 'cleanup "$?"' EXIT

case "$release_output" in
    "$project_root"/dist/*) ;;
    *) echo "Invalid output directory: $release_output" >&2; exit 1 ;;
esac
rm -rf -- "$release_output"
mkdir -p "$release_output" "$MPLCONFIGDIR"

if ! "$python" -c 'import PySide6' >/dev/null 2>&1; then
    echo "GUI build requires: uv sync --frozen --extra gui --group dev" >&2
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

    "$python" "$project_root/packaging/clean_build.py" --root "$project_root"
    mkdir -p "$MPLCONFIGDIR"
    MDHELPER_GUI_BUILD="$gui" "$python" -m PyInstaller \
        --clean \
        --noconfirm \
        --distpath "$application_output" \
        --workpath "$work" \
        "$project_root/packaging/posix/mdhelper.spec"
    if [[ "$gui" == 1 ]]; then
        notices+=(--extra gui)
    fi
    local application="$application_output/mdhelper"
    if [[ "$platform" == macos ]]; then
        application="$application_output/MDHelper.app"
        test "$(lipo -archs "$application/Contents/MacOS/mdhelper")" = arm64
        codesign --verify --deep --strict "$application"
    fi

    "$python" "$project_root/packaging/frozen_audit.py" \
        --application "$application" \
        --platform "$audit_platform" \
        --max-size-mb "$max_size_mb"

    mkdir -p "$root"
    if [[ "$platform" == macos ]]; then
        ditto "$application" "$root/MDHelper.app"
    else
        cp "$application" "$root/mdhelper"
    fi
    cp "$project_root/LICENSE" "$root/LICENSE"
    cp "$project_root/README.md" "$root/README.md"
    cp "$project_root/README.zh-CN.md" "$root/README.zh-CN.md"
    cp "$project_root/config.example.toml" "$root/config.example.toml"
    cp "$project_root/config.example.toml" "$root/config.toml"
    cp -R "$project_root/docs" "$root/docs"
    cp -R "$project_root/schemas" "$root/schemas"
    "$python" "${notices[@]}"

    if [[ "$platform" == macos ]]; then
        local artifact="$release_output/$name.dmg"
        local dmg_options=(--source "$root" --artifact "$artifact" --version "$version")
        if [[ -n "$smoke_request" ]]; then
            dmg_options+=(--request "$smoke_request")
        fi
        MAX_ARTIFACT_SIZE_MB="$max_size_mb" \
            "$python" "$project_root/packaging/posix/dmg.py" "${dmg_options[@]}"
        if [[ ! -s "$artifact" ]]; then
            echo "Missing or empty release artifact: $artifact" >&2
            exit 1
        fi
        return
    fi

    tar -C "$stage" -czf "$archive" "$name"
    "$python" "$project_root/packaging/frozen_audit.py" \
        --artifact "$archive" \
        --platform "$audit_platform" \
        --max-size-mb "$max_size_mb"
    if [[ -n "$smoke_request" ]]; then
        mkdir -p "$verified"
        tar -C "$verified" -xzf "$archive"
        "$python" "$project_root/packaging/smoke_check.py" archive-root \
            --root "$verified" --expected-name "$name"
        PYTHON="$python" bash "$project_root/packaging/posix/smoke.sh" \
            "$verified/$name" \
            "$audit_platform" \
            "$smoke_request"
    fi
    printf '%s %s archive: %s\n' "$platform" "$variant" "$archive"
}

if [[ "$platform" == linux ]]; then
    build_variant headless 0 "MDHelper-$version-$label" linux
    build_variant gui 1 "MDHelper-$version-$label-GUI" linux-gui
else
    build_variant gui 1 "MDHelper-$version-$label" macos
fi
build_status=0
