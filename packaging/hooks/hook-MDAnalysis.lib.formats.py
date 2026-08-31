from importlib.machinery import EXTENSION_SUFFIXES
from importlib.metadata import distribution
from pathlib import Path

root = Path(distribution("MDAnalysis").locate_file("MDAnalysis/lib/formats"))


def extension_name(path: Path) -> str | None:
    for suffix in sorted(EXTENSION_SUFFIXES, key=len, reverse=True):
        if path.name.endswith(suffix):
            return path.name.removesuffix(suffix)
    return None


hiddenimports = sorted(
    f"MDAnalysis.lib.formats.{name}"
    for path in root.iterdir()
    if (name := extension_name(path)) is not None
)
