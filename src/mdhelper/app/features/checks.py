"""System inspection feature."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from mdhelper.app.context import ApplicationContext
from mdhelper.core.system import SystemSummary
from mdhelper.services.selection import index_group_sizes
from mdhelper.services.system import summarize_source, trajectory_cache


class CheckFeature:
    def __init__(self, context: ApplicationContext):
        self.context = context

    def inspect_system(
        self,
        topology: str,
        trajectory: str,
        index_file: str | None = None,
        cache_dir: str | Path | None = None,
        project_root: str | Path | None = None,
    ) -> SystemSummary:
        with trajectory_cache(cache_dir):
            source = self.context.trajectory_loader(
                topology, trajectory, "auto", None, None
            )
        try:
            summary = summarize_source(source, project_root)
            if index_file:
                summary = replace(
                    summary,
                    index_groups=index_group_sizes(index_file, len(source.atoms)),
                )
            return summary
        finally:
            source.close()
