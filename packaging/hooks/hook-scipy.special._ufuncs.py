from importlib.machinery import EXTENSION_SUFFIXES
from importlib.metadata import distribution
from pathlib import Path

root = Path(distribution("scipy").locate_file("scipy/special"))


def extension_name(path: Path) -> str | None:
    for suffix in sorted(EXTENSION_SUFFIXES, key=len, reverse=True):
        if path.name.endswith(suffix):
            return path.name.removesuffix(suffix)
    return None


available = {
    name for path in root.iterdir() if (name := extension_name(path)) is not None
}
candidates = ("_ufuncs_cxx", "_cdflib", "_special_ufuncs")
hiddenimports = [f"scipy.special.{name}" for name in candidates if name in available]
