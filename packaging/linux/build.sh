#!/usr/bin/env bash
set -euo pipefail

python=${PYTHON:-python}
max_size_mb=${MAX_ARTIFACT_SIZE_MB:-256}
project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
release_output="$project_root/dist/linux"
work="$project_root/build/pyinstaller-linux"
version=$($python -c 'import mdhelper; print(mdhelper.__version__)')
name="MDHelper-$version-Linux-x86_64"
archive="$release_output/$name.tar.gz"
stage=$(mktemp -d)
application_output="$stage/application"
export MPLCONFIGDIR="$work/matplotlib"

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

"$python" -m PyInstaller \
    --clean \
    --noconfirm \
    --distpath "$application_output" \
    --workpath "$work" \
    "$project_root/packaging/linux/mdhelper.spec"

"$python" "$project_root/packaging/frozen_audit.py" \
    --application "$application_output/mdhelper" \
    --platform linux \
    --max-size-mb "$max_size_mb"

root="$stage/$name"
mkdir -p "$root"
cp "$application_output/mdhelper" "$root/mdhelper"
cp "$project_root/LICENSE" "$root/LICENSE"
cp "$project_root/README.md" "$root/README.md"
cp "$project_root/README.zh-CN.md" "$root/README.zh-CN.md"
cp "$project_root/config.example.toml" "$root/config.example.toml"
cp "$project_root/config.example.toml" "$root/config.toml"
cp -R "$project_root/docs" "$root/docs"
cp -R "$project_root/schemas" "$root/schemas"
"$python" "$project_root/packaging/generate_notices.py" \
    --output "$root/THIRD_PARTY_NOTICES.json"

tar -C "$stage" -czf "$archive" "$name"
"$python" "$project_root/packaging/frozen_audit.py" \
    --artifact "$archive" \
    --platform linux \
    --max-size-mb "$max_size_mb"
mkdir -p "$stage/verified"
tar -C "$stage/verified" -xzf "$archive"
"$project_root/packaging/linux/smoke.sh" "$stage/verified/$name"
printf 'Linux archive: %s\n' "$archive"
