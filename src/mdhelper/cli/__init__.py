"""Command-line adapter package."""

from .main import main
from .parser import build_parser, parse_args

__all__ = ["build_parser", "main", "parse_args"]
