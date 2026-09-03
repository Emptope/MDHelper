"""Small, dependency-free terminal interaction primitives."""

from __future__ import annotations

import math
import sys
from collections.abc import Sequence
from typing import TextIO, TypeVar

T = TypeVar("T")
_CONTENT_WIDTH = 76


class EndOfInput(EOFError):
    """Raised when an interactive input stream is closed."""


class Terminal:
    def __init__(
        self,
        input_stream: TextIO | None = None,
        output_stream: TextIO | None = None,
    ):
        self.input = sys.stdin if input_stream is None else input_stream
        self.output = sys.stdout if output_stream is None else output_stream

    @property
    def interactive(self) -> bool:
        return bool(getattr(self.input, "isatty", lambda: False)()) and bool(
            getattr(self.output, "isatty", lambda: False)()
        )

    def write(self, text: str = "") -> None:
        self.output.write(f"{text}\n")
        self.output.flush()

    def heading(
        self,
        title: str,
        width: int = _CONTENT_WIDTH,
        *,
        blank_before: bool = False,
    ) -> None:
        if blank_before:
            self.write()
        self.write(f"*** {title} ***".center(width).rstrip())

    def panel(self, lines: Sequence[str], width: int = _CONTENT_WIDTH) -> None:
        inner_width = max(width - 2, max((len(line) for line in lines), default=0))
        border = f"+{'-' * inner_width}+"
        padding = f"|{' ' * inner_width}|"
        self.write(border)
        self.write(padding)
        for line in lines:
            self.write(f"|{line.center(inner_width)}|")
        self.write(padding)
        self.write(border)

    def _write_grid(self, items: Sequence[str], width: int = _CONTENT_WIDTH) -> None:
        if not items:
            return
        gap = "  "
        cell_width = max(len(item) for item in items)
        columns = min(len(items), max(1, (width + len(gap)) // (cell_width + len(gap))))
        for start in range(0, len(items), columns):
            row = items[start : start + columns]
            self.write(gap.join(item.ljust(cell_width) for item in row).rstrip())

    def ask(
        self,
        prompt: str,
        default: str | None = None,
        *,
        allow_empty: bool = False,
        blank_before: bool = False,
        blank_after: bool = True,
    ) -> str:
        suffix = f" [{default}]" if default is not None else ""
        if blank_before:
            self.write()
        while True:
            label = f"{prompt}{suffix}: " if prompt else f">{suffix} "
            self.output.write(label)
            self.output.flush()
            line = self.input.readline()
            if line == "":
                raise EndOfInput("The terminal input stream was closed.")
            # Terminal echo ends an interactive input line. Piped input still needs an
            # explicit line ending so subsequent output does not join the prompt.
            if blank_after or not self.interactive:
                self.write()
            value = line.strip()
            if value:
                return value
            if default is not None:
                return default
            if allow_empty:
                return ""
            self.write("A value is required.")

    def number(
        self,
        prompt: str,
        default: float,
        *,
        minimum: float | None = None,
    ) -> float:
        while True:
            value = self.ask(prompt, f"{default:g}")
            try:
                parsed = float(value)
            except ValueError:
                self.write("Enter a number.")
                continue
            if not math.isfinite(parsed):
                self.write("Enter a finite number.")
                continue
            if minimum is not None and parsed < minimum:
                self.write(f"Enter a value greater than or equal to {minimum:g}.")
                continue
            return parsed

    def integer(
        self,
        prompt: str,
        default: int | None,
        *,
        minimum: int | None = None,
        allow_empty: bool = False,
    ) -> int | None:
        shown = None if default is None else str(default)
        while True:
            value = self.ask(prompt, shown, allow_empty=allow_empty)
            if not value and allow_empty:
                return None
            try:
                parsed = int(value)
            except ValueError:
                self.write("Enter an integer.")
                continue
            if minimum is not None and parsed < minimum:
                self.write(f"Enter an integer greater than or equal to {minimum}.")
                continue
            return parsed

    def confirm(self, prompt: str, default: bool = False) -> bool:
        shown = "Y/n" if default else "y/N"
        while True:
            value = self.ask(f"{prompt} ({shown})", "y" if default else "n").casefold()
            if value in {"y", "yes"}:
                return True
            if value in {"n", "no"}:
                return False
            self.write("Enter y or n.")

    def menu(
        self,
        title: str,
        options: Sequence[tuple[str, T]],
        *,
        back: bool = True,
    ) -> T | None:
        self.write()
        self.heading(title)
        for label, value in options:
            self.write(f" {value!s:>2}  {label}")
        if back:
            self.write("  0  Return")
        values = {str(value).casefold(): value for _, value in options}
        self.write()
        while True:
            choice = self.ask("").casefold()
            if back and choice == "0":
                return None
            if choice in values:
                return values[choice]
            self.write("Choose one of the listed menu numbers.")

    def choose(
        self,
        title: str,
        options: Sequence[tuple[str, T]],
        default: T | None = None,
    ) -> T:
        self.write()
        self.heading(title)
        numbered = list(enumerate(options, 1))
        for number, (label, value) in numbered:
            marker = " *" if default is not None and value == default else ""
            self.write(f" {number:>2}  {label}{marker}")
        self.write()
        while True:
            shown = None
            if default is not None:
                shown = str(next(number for number, (_, value) in numbered if value == default))
            selected = self.ask("", shown)
            try:
                index = int(selected) - 1
            except ValueError:
                self.write("Enter a listed number.")
                continue
            if 0 <= index < len(options):
                return options[index][1]
            self.write("Enter a listed number.")

    def select_many(
        self,
        title: str,
        options: Sequence[tuple[str, T]],
        selected: Sequence[T] = (),
    ) -> tuple[T, ...]:
        """Toggle values while preserving the order in which they were selected."""

        values = [value for _, value in options]
        chosen: list[T] = []
        for value in selected:
            if value in values and value not in chosen:
                chosen.append(value)
        while True:
            self.write()
            self.heading(title)
            width = max(2, len(str(len(options))))
            self._write_grid(
                tuple(
                    f" {number:>{width}}  {'[x]' if value in chosen else '[ ]'} {label}"
                    for number, (label, value) in enumerate(options, 1)
                )
            )
            self.write("  a  Select all")
            self.write("  c  Clear")
            self.write("  0  Done")
            self.write()
            action = self.ask("", "0").casefold()
            if action == "0":
                return tuple(chosen)
            if action == "a":
                chosen.extend(value for value in values if value not in chosen)
                continue
            if action == "c":
                chosen.clear()
                continue
            parts = action.replace(",", " ").split()
            try:
                indexes = [int(part) - 1 for part in parts]
            except ValueError:
                self.write("Enter listed numbers, a, c, or 0.")
                continue
            if not indexes or any(index < 0 or index >= len(options) for index in indexes):
                self.write("Enter listed numbers, a, c, or 0.")
                continue
            for index in indexes:
                value = options[index][1]
                if value in chosen:
                    chosen.remove(value)
                else:
                    chosen.append(value)

    def progress(self, current: int, total: int | None, message: str) -> None:
        total_text = "?" if total is None else str(total)
        if self.interactive:
            self.output.write(f"\r[{current}/{total_text}] {message[:56]:56}")
            self.output.flush()
        else:
            self.write(f"[{current}/{total_text}] {message}")

    def finish_progress(self) -> None:
        if self.interactive:
            self.write()
