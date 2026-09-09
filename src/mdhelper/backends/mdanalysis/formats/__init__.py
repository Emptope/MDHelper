"""Local reader selection without modifying dependency registries."""

from __future__ import annotations

from typing import Any


def get_reader(filename: str) -> Any:
    from MDAnalysis.coordinates.core import get_reader_for

    reader = get_reader_for(filename)
    if reader.format == "TPR":
        from mdhelper.backends.mdanalysis.formats.tpr import TprReader

        return TprReader
    return reader


def get_parser(filename: str) -> Any:
    from MDAnalysis.core._get_readers import get_parser_for

    parser = get_parser_for(filename)
    if parser.format == "TPR":
        from mdhelper.backends.mdanalysis.formats.tpr import TprParser

        return TprParser
    return parser
