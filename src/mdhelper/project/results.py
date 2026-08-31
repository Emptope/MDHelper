"""Transactional project-result commits and verified result loading."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mdhelper.core.analysis import AnalysisRequest, AnalysisResult
from mdhelper.core.errors import ConfigurationError
from mdhelper.project.inputs import InputRepository
from mdhelper.project.manifests import ManifestRepository
from mdhelper.project.storage import atomic_json
from mdhelper.services.provenance import sha256_file


class ResultRepository:
    def __init__(
        self,
        root: Path,
        manifests: ManifestRepository,
        inputs: InputRepository,
    ):
        self.root = root
        self.manifests = manifests
        self.inputs = inputs

    def _path(self, entry: dict[str, Any]) -> Path | None:
        value = entry.get("result")
        if not isinstance(value, str) or not value:
            return None
        path = (self.root / value).resolve()
        try:
            path.relative_to(self.root / "results" / "data")
        except ValueError:
            return None
        return path

    def commit(
        self,
        manifest: dict[str, Any],
        request: AnalysisRequest,
        result: AnalysisResult,
    ) -> tuple[dict[str, Any], Path]:
        result.validate()
        request.validate()
        self.manifests.ensure_layout()
        if result.request != request.to_dict():
            raise ConfigurationError(
                "The committed request does not match the request embedded in the result.",
                "Commit the exact request that produced this result.",
            )
        input_records = self.inputs.result_records(manifest, request, result)
        result_path = self.root / "results" / "data" / f"{result.analysis_id}.json"
        if result_path.exists() or any(
            entry.get("analysis_id") == result.analysis_id
            for entry in manifest.get("analyses", [])
        ):
            raise ConfigurationError(
                f"Analysis result {result.analysis_id} is already committed.",
                "Keep each analysis_id unique; reopen the existing result instead.",
            )
        atomic_json(result_path, result.to_dict())
        entry = {
            "analysis_id": result.analysis_id,
            "analysis_type": result.analysis_type,
            "method_version": result.method_version,
            "status": result.status,
            "request": request.to_dict(),
            "result": os.path.relpath(result_path, self.root),
            "result_sha256": sha256_file(result_path),
            "committed_at": datetime.now(UTC).isoformat(),
        }
        updated = dict(manifest)
        updated["inputs"] = {
            **manifest["inputs"],
            **{
                role: record
                for role, record in input_records.items()
                if role not in manifest["inputs"]
            },
        }
        if request.species_roles:
            updated["species_roles"] = dict(request.species_roles)
        integration_runs = result.provenance.get("integration_runs", [])
        if isinstance(integration_runs, list):
            updated["integration_runs"] = [
                *manifest.get("integration_runs", []),
                *(dict(item) for item in integration_runs if isinstance(item, dict)),
            ]
        updated["analyses"] = [*manifest.get("analyses", []), entry]
        try:
            updated = self.manifests.commit(updated)
        except BaseException:
            result_path.unlink(missing_ok=True)
            raise
        return updated, result_path

    def list(self, manifest: dict[str, Any]) -> tuple[dict[str, object], ...]:
        entries = manifest.get("analyses", [])
        if not isinstance(entries, list):
            raise ConfigurationError("Project field 'analyses' must be an array.")
        results: list[dict[str, object]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            item: dict[str, object] = dict(entry)
            path = self._path(entry)
            item["available"] = path is not None and path.is_file()
            results.append(item)
        return tuple(results)

    def load(self, manifest: dict[str, Any], analysis_id: str) -> AnalysisResult:
        for entry in manifest.get("analyses", []):
            if entry.get("analysis_id") != analysis_id:
                continue
            path = self._path(entry)
            if path is None:
                raise ConfigurationError(
                    f"Analysis result path is invalid: {analysis_id}",
                    "Remove the invalid project entry or restore a path inside the project.",
                )
            if not path.is_file():
                raise ConfigurationError(
                    f"Analysis result file is missing: {analysis_id}",
                    "Rerun the analysis to create a new saved result.",
                )
            try:
                expected = entry["result_sha256"]
                if sha256_file(path) != expected:
                    raise ConfigurationError(
                        f"Analysis result fingerprint changed: {analysis_id}",
                        "Restore the committed result or rerun the analysis.",
                    )
                value = json.loads(path.read_text(encoding="utf-8"))
                return AnalysisResult.from_dict(value)
            except ConfigurationError:
                raise
            except (OSError, json.JSONDecodeError, TypeError) as exc:
                raise ConfigurationError(
                    f"Could not load analysis result {analysis_id}.",
                    details={"exception": f"{type(exc).__name__}: {exc}"},
                ) from exc
        raise ConfigurationError(f"Analysis result not found: {analysis_id}")
