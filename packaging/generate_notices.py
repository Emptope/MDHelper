from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path

from packaging.requirements import Requirement


def _license(metadata: importlib.metadata.PackageMetadata) -> str:
    declared = metadata.get("License-Expression") or metadata.get("License")
    if declared and declared.strip():
        return " ".join(declared.split())
    classifiers = metadata.get_all("Classifier") or []
    licenses = [
        classifier.removeprefix("License :: OSI Approved :: ")
        for classifier in classifiers
        if classifier.startswith("License :: OSI Approved :: ")
    ]
    return "; ".join(licenses) if licenses else "unknown"


def dependency_notices(root_distribution: str) -> list[dict[str, str]]:
    notices: list[dict[str, str]] = []
    pending: list[str] = []
    for raw_requirement in importlib.metadata.requires(root_distribution) or []:
        requirement = Requirement(raw_requirement)
        if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
            continue
        pending.append(requirement.name)
    visited: set[str] = set()
    while pending:
        dependency = pending.pop()
        canonical = dependency.casefold().replace("_", "-")
        if canonical in visited:
            continue
        visited.add(canonical)
        distribution = importlib.metadata.distribution(dependency)
        metadata = distribution.metadata
        name = metadata.get("Name")
        if not name:
            continue
        notices.append(
            {
                "name": name,
                "version": distribution.version,
                "license": _license(metadata),
                "home_page": metadata.get("Project-URL") or metadata.get("Home-page") or "",
            }
        )
        for raw_requirement in distribution.requires or []:
            requirement = Requirement(raw_requirement)
            if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
                continue
            pending.append(requirement.name)
    return sorted(notices, key=lambda item: item["name"].casefold())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--distribution", default="mdhelper")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    dependencies = dependency_notices(args.distribution)
    unknown = [item["name"] for item in dependencies if item["license"] == "unknown"]
    if unknown:
        parser.error(f"Dependencies have no declared license metadata: {', '.join(unknown)}")
    args.output.write_text(
        json.dumps(
            {
                "format_version": 1,
                "root_distribution": args.distribution,
                "dependencies": dependencies,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
