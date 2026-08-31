"""VMD executable-family integration."""

from __future__ import annotations

import os
import re
from pathlib import Path

from mdhelper.integrations.models import IntegrationAdapter


class VmdAdapter(IntegrationAdapter):
    name = "vmd"
    display_name = "VMD"

    def candidate_names(self) -> tuple[str, ...]:
        return ("vmd.exe",) if os.name == "nt" else ("vmd",)

    def environment_paths(self, environment: dict[str, str]) -> tuple[tuple[str, str], ...]:
        value = environment.get("MDHELPER_VMD")
        return (("MDHELPER_VMD", value),) if value else ()

    def candidate_paths(self, environment: dict[str, str]) -> tuple[str, ...]:
        names = self.candidate_names()
        if os.name == "nt":
            roots = tuple(
                Path(value) / "University of Illinois" / "VMD"
                for key in ("ProgramFiles", "ProgramFiles(x86)")
                if (value := environment.get(key))
            )
            return tuple(str(root / name) for root in roots for name in names)
        return tuple(
            str(Path(root) / name)
            for root in ("/usr/local/bin", "/opt/vmd/bin")
            for name in names
        )

    def version_detect(self) -> tuple[str, str]:
        return ("quit\n", ".tcl")

    def version_arguments(self, detect_path: str | None = None) -> tuple[str, ...]:
        if detect_path is None:
            raise ValueError("VMD version detection requires a detect file.")
        return ("-dispdev", "text", "-e", detect_path)

    def parse_version(self, stdout: str, stderr: str, exit_code: int) -> str | None:
        if exit_code != 0:
            return None
        output = f"{stdout}\n{stderr}"
        match = re.search(r"VMD[^\r\n]*?version\s+([^\s]+)", output, flags=re.IGNORECASE)
        return match.group(1) if match else None

    def default_capabilities(self) -> tuple[str, ...]:
        return ("script", "trajectory")

    def environment_keys(self) -> frozenset[str]:
        return frozenset({"VMDDIR", "TCL_LIBRARY", "TK_LIBRARY"})

    def provenance_environment_keys(self) -> frozenset[str]:
        return frozenset({"VMDDIR"})
