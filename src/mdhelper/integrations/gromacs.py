"""GROMACS executable-family adapter."""

from __future__ import annotations

import os
import re
from pathlib import Path

from mdhelper.integrations.registry import IntegrationAdapter

_FRAME_PROGRESS = re.compile(
    r"(?i)(?:reading|last)\s+frame\s+(\d+)\s+time\s+([-+0-9.eE]+)"
)
_LAST_FRAME = re.compile(r"(?i)last\s+frame\s+(\d+)\s+time\s+[-+0-9.eE]+")
_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_ERROR_HEADING = re.compile(
    r"(?:Error in user input|Fatal error|Inconsistency in user input):",
    flags=re.IGNORECASE,
)
_MAKE_NDX_STRUCTURE_SUFFIXES = (
    ".gro",
    ".g96",
    ".pdb",
    ".brk",
    ".ent",
    ".esp",
    ".tpr",
)


def _output_line(value: str) -> str | None:
    for raw in reversed(value.splitlines()):
        line = _ANSI.sub("", raw)
        line = "".join(" " if ord(character) < 32 else character for character in line)
        if line := line.strip():
            return line
    return None


def output_message(stdout: str, stderr: str) -> str | None:
    line = _output_line(stderr) or _output_line(stdout)
    return f"GROMACS: {line}" if line is not None else None


def error_message(stdout: str, stderr: str) -> str | None:
    """Extract the native GROMACS error block from captured process output."""

    for value in (stderr, stdout):
        lines = _ANSI.sub("", value).splitlines()
        starts = tuple(
            index
            for index, line in enumerate(lines)
            if _ERROR_HEADING.fullmatch(line.strip())
        )
        if not starts:
            continue
        result: list[str] = []
        for raw in lines[starts[-1] :]:
            line = "".join(
                " " if ord(character) < 32 else character for character in raw
            ).strip()
            if line.startswith(("For more information", "----------------")):
                break
            if line:
                result.append(line)
        if result:
            return "\n".join(result)
    return None


def frame_progresses(stdout: str, stderr: str) -> tuple[tuple[int, float], ...]:
    values: list[tuple[int, float]] = []
    for match in _FRAME_PROGRESS.finditer(f"{stdout}\n{stderr}"):
        try:
            values.append((int(match.group(1)), float(match.group(2))))
        except ValueError:
            continue
    return tuple(values)


def frame_progress(stdout: str, stderr: str) -> tuple[int, float] | None:
    values = frame_progresses(stdout, stderr)
    return values[-1] if values else None


def frame_count(stdout: str, stderr: str) -> int | None:
    matches = tuple(_LAST_FRAME.finditer(f"{stdout}\n{stderr}"))
    return int(matches[-1].group(1)) + 1 if matches else None


class GromacsAdapter(IntegrationAdapter):
    name = "gromacs"
    display_name = "GROMACS"

    def candidate_names(self) -> tuple[str, ...]:
        return ("gmx.exe", "gmx_mpi.exe") if os.name == "nt" else ("gmx", "gmx_mpi")

    def environment_paths(self, environment: dict[str, str]) -> tuple[tuple[str, str], ...]:
        candidates: list[tuple[str, str]] = []
        if environment.get("MDHELPER_GROMACS"):
            candidates.append(("MDHELPER_GROMACS", environment["MDHELPER_GROMACS"]))
        if environment.get("GMXBIN"):
            candidates.extend(
                ("GMXBIN", str(Path(environment["GMXBIN"]) / name))
                for name in self.candidate_names()
            )
        return tuple(candidates)

    def candidate_paths(self, environment: dict[str, str]) -> tuple[str, ...]:
        names = self.candidate_names()
        if os.name == "nt":
            roots = tuple(
                Path(value) / "GROMACS" / "bin"
                for key in ("ProgramFiles", "ProgramFiles(x86)")
                if (value := environment.get(key))
            )
            return tuple(str(root / name) for root in roots for name in names)
        return tuple(
            str(Path(root) / name)
            for root in ("/usr/local/gromacs/bin", "/opt/gromacs/bin")
            for name in names
        )

    def parse_version(self, stdout: str, stderr: str, exit_code: int) -> str | None:
        if exit_code != 0:
            return None
        output = f"{stdout}\n{stderr}"
        if "GROMACS" not in output.upper():
            return None
        match = re.search(r"GROMACS version:\s*([^\r\n]+)", output, flags=re.IGNORECASE)
        return match.group(1).strip() if match else "unknown"

    def capability_arguments(self) -> tuple[str, ...]:
        return ("help", "commands")

    def parse_capabilities(
        self, stdout: str, stderr: str, exit_code: int
    ) -> tuple[str, ...]:
        if exit_code != 0:
            return ()
        output = f"{stdout}\n{stderr}"
        table = tuple(
            match.group(1).casefold()
            for match in re.finditer(
                r"(?m)^[ \t]{4}([a-z][a-z0-9_-]*)[ \t]{2,}\S",
                output,
            )
        )
        if table:
            return tuple(dict.fromkeys(table))
        commands: list[str] = []
        seen: set[str] = set()
        for match in re.finditer(
            r"(?im)^\s*gmx(?:\.exe)?\s+([a-z][a-z0-9_-]*)\b",
            output,
        ):
            command = match.group(1).casefold()
            if command not in seen:
                seen.add(command)
                commands.append(command)
        return tuple(commands)

    def file_suffixes(self, command: str, option: str) -> tuple[str, ...]:
        if command.casefold() == "make_ndx" and option.casefold() == "-f":
            return _MAKE_NDX_STRUCTURE_SUFFIXES
        return ()

    def environment_keys(self) -> frozenset[str]:
        return frozenset(
            {
                "GMXBIN",
                "GMXDATA",
                "GMXLIB",
                "GMXLDLIB",
                "OMP_NUM_THREADS",
                "LD_LIBRARY_PATH",
                "DYLD_LIBRARY_PATH",
            }
        )

    def provenance_environment_keys(self) -> frozenset[str]:
        return frozenset({"GMXBIN", "GMXDATA", "GMXLIB", "OMP_NUM_THREADS"})
