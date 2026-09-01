"""Transactional project-result commits and verified result loading."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mdhelper.core.analysis import AnalysisRequest, AnalysisResult, RadialRequest
from mdhelper.core.errors import ConfigurationError
from mdhelper.project.inputs import InputRepository
from mdhelper.project.manifests import ManifestRepository
from mdhelper.project.runs import RunRepository
from mdhelper.project.storage import atomic_json
from mdhelper.services.provenance import sha256_file

_RunRecords = list[dict[str, Any]]


class ResultRepository:
    def __init__(
        self,
        root: Path,
        manifests: ManifestRepository,
        inputs: InputRepository,
        runs: RunRepository,
    ):
        self.root = root
        self.manifests = manifests
        self.inputs = inputs
        self.runs = runs

    def _path(self, entry: dict[str, Any]) -> Path | None:
        analysis_id = entry.get("analysis_id")
        if not isinstance(analysis_id, str) or not analysis_id:
            return None
        path = (self.root / "results" / "data" / f"{analysis_id}.json").resolve()
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
        result_path = self._path({"analysis_id": result.analysis_id})
        if result_path is None:
            raise ConfigurationError("Analysis result ID cannot form a project result path.")
        if result_path.exists() or any(
            entry.get("analysis_id") == result.analysis_id
            for entry in manifest.get("analyses", [])
        ):
            raise ConfigurationError(
                f"Analysis result {result.analysis_id} is already committed.",
                "Keep each analysis_id unique; reopen the existing result instead.",
            )
        run_records = self._run_records(result.provenance)
        stream_paths: list[Path] = []
        try:
            stored_runs, stream_paths = self.runs.store(run_records, result.analysis_id)
            stored_result = result.to_dict()
            if stored_runs:
                stored_result["provenance"]["integration_runs"] = stored_runs
            atomic_json(result_path, stored_result)
            entry = {
                "analysis_id": result.analysis_id,
                "analysis_type": result.analysis_type,
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
            if isinstance(request, RadialRequest) and request.species_roles:
                updated["species_roles"] = dict(request.species_roles)
            updated["analyses"] = [*manifest.get("analyses", []), entry]
            updated = self.manifests.commit(updated)
        except BaseException:
            result_path.unlink(missing_ok=True)
            self.runs.remove(stream_paths)
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
            if item["available"]:
                try:
                    result = self._load_entry(entry)
                except ConfigurationError:
                    item["available"] = False
                else:
                    item["request"] = result.request
                    item["method_version"] = result.method_version
            results.append(item)
        return tuple(results)

    def load(self, manifest: dict[str, Any], analysis_id: str) -> AnalysisResult:
        for entry in manifest.get("analyses", []):
            if entry.get("analysis_id") != analysis_id:
                continue
            return self._load_entry(entry)
        raise ConfigurationError(f"Analysis result not found: {analysis_id}")

    def _load_entry(self, entry: dict[str, Any]) -> AnalysisResult:
        analysis_id = str(entry.get("analysis_id", ""))
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
            if sha256_file(path) != entry["result_sha256"]:
                raise ConfigurationError(
                    f"Analysis result fingerprint changed: {analysis_id}",
                    "Restore the committed result or rerun the analysis.",
                )
            value = json.loads(path.read_text(encoding="utf-8"))
            provenance = value.get("provenance")
            if isinstance(provenance, dict):
                stored_runs = self._run_records(provenance)
                if stored_runs:
                    provenance["integration_runs"] = self.runs.hydrate(
                        stored_runs, analysis_id
                    )
            result = AnalysisResult.from_dict(value)
            if result.analysis_id != analysis_id:
                raise ConfigurationError(
                    f"Analysis result identity does not match its project entry: {analysis_id}"
                )
            if result.analysis_type != entry["analysis_type"]:
                raise ConfigurationError(
                    f"Analysis result type does not match its project entry: {analysis_id}"
                )
            return result
        except ConfigurationError:
            raise
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            raise ConfigurationError(
                f"Could not load analysis result {analysis_id}.",
                details={"exception": f"{type(exc).__name__}: {exc}"},
            ) from exc

    @staticmethod
    def _run_records(provenance: dict[str, Any]) -> _RunRecords:
        raw = provenance.get("integration_runs")
        if raw is None:
            return []
        if not isinstance(raw, list) or any(not isinstance(item, dict) for item in raw):
            raise ConfigurationError(
                "Analysis result integration runs must be an array of objects."
            )
        return [dict(item) for item in raw]
