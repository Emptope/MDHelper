"""GROMACS executable-family adapter."""

from __future__ import annotations

import os
import re
from pathlib import Path

from mdhelper.integrations.models import IntegrationAdapter


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
