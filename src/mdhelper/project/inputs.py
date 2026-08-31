"""Project input records, resolution, fingerprint checks, and relocation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, TypedDict

from mdhelper.core.analysis import AnalysisRequest, AnalysisResult
from mdhelper.core.errors import ConfigurationError, InputFileError
from mdhelper.services.provenance import sha256_file


class InputRecord(TypedDict):
    absolute_path: str
    relative_path: str | None
    sha256: str


class InputRepository:
    def __init__(self, root: Path):
        self.root = root

    def record(self, path: str | Path) -> InputRecord:
        resolved = Path(path).expanduser().resolve()
        if not resolved.is_file():
            raise InputFileError(f"Project input does not exist: {resolved}")
        try:
            relative_path: str | None = os.path.relpath(resolved, self.root)
        except ValueError:
            relative_path = None
        return {
            "absolute_path": str(resolved),
            "relative_path": relative_path,
            "sha256": sha256_file(resolved),
        }

    def resolve(self, record: InputRecord, verify_fingerprint: bool = True) -> Path:
        candidates: list[Path] = []
        if record["relative_path"] is not None:
            candidates.append((self.root / record["relative_path"]).resolve())
        candidates.append(Path(record["absolute_path"]))
        mismatched: list[str] = []
        for candidate in candidates:
            if not candidate.is_file():
                continue
            if verify_fingerprint and sha256_file(candidate) != record["sha256"]:
                mismatched.append(str(candidate))
                continue
            return candidate.resolve()
        if mismatched:
            raise InputFileError(
                "A project input exists but its content fingerprint changed.",
                "Restore the original file or explicitly relocate the project input.",
                {"mismatched_paths": mismatched, "expected_sha256": record["sha256"]},
            )
        raise InputFileError(
            "A project input could not be located.",
            "Move the input next to the project or use project relocation.",
            {"tried": [str(path) for path in candidates]},
        )

    def resolve_all(
        self, records: dict[str, InputRecord], verify_fingerprints: bool = True
    ) -> dict[str, Path]:
        return {
            role: self.resolve(record, verify_fingerprints)
            for role, record in records.items()
        }

    def relocate(
        self, role: str, records: dict[str, InputRecord], path: str | Path
    ) -> InputRecord:
        if role not in records:
            raise ConfigurationError(f"Unknown project input role: {role}")
        current = records[role]
        relocated = self.record(path)
        if relocated["sha256"] != current["sha256"]:
            raise InputFileError(
                f"The selected {role} file does not match the project's recorded input.",
                "Select the moved original file. Replacing project inputs requires "
                "a new project.",
                {
                    "expected_sha256": current["sha256"],
                    "selected_sha256": relocated["sha256"],
                    "selected_path": relocated["absolute_path"],
                },
            )
        return relocated

    def result_records(
        self,
        manifest: dict[str, Any],
        request: AnalysisRequest,
        result: AnalysisResult,
    ) -> dict[str, InputRecord]:
        if request.analysis_type == "energy":
            assert request.energy_file is not None
            requested: dict[str, str] = {"energy": request.energy_file}
        else:
            requested = {
                "topology": request.topology,
                "trajectory": request.trajectory,
            }
            if request.index_file is not None:
                requested["index"] = request.index_file
        provenance_files = result.provenance.get("input_files")
        provenance_hashes = result.provenance.get("input_sha256")
        if not isinstance(provenance_files, dict) or not isinstance(provenance_hashes, dict):
            raise ConfigurationError(
                "The analysis result lacks auditable input provenance.",
                "Only commit results produced through the shared application service.",
            )
        records: dict[str, InputRecord] = {}
        for role, request_path in requested.items():
            record = self.record(request_path)
            project_record = manifest["inputs"].get(role)
            if project_record is not None and project_record["sha256"] != record["sha256"]:
                raise InputFileError(
                    f"The analysis {role} does not match the project's recorded input.",
                    "Create a new project for different inputs.",
                    {
                        "project_sha256": project_record["sha256"],
                        "analysis_sha256": record["sha256"],
                    },
                )
            provenance_path = provenance_files.get(role)
            provenance_digest = (
                provenance_hashes.get(provenance_path)
                if isinstance(provenance_path, str)
                else None
            )
            if provenance_digest != record["sha256"]:
                raise ConfigurationError(
                    f"The result provenance does not match its {role} input.",
                    "Rerun the analysis through the shared application service.",
                    {
                        "input_sha256": record["sha256"],
                        "provenance_sha256": provenance_digest,
                    },
                )
            records[role] = record
        return records
