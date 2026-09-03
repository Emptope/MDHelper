"""System inspection state for the desktop GUI."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from mdhelper.core.species import SpeciesRoleSuggestion


class InspectionPhase(Enum):
    EMPTY = "empty"
    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"


@dataclass
class InspectionState:
    phase: InspectionPhase = InspectionPhase.EMPTY
    pending_roles: dict[str, str] = field(default_factory=dict)
    suggestions: dict[str, SpeciesRoleSuggestion] = field(default_factory=dict)
    role_sources: dict[str, str] = field(default_factory=dict)

    def schedule(self, roles: dict[str, str]) -> None:
        if self.phase is InspectionPhase.RUNNING:
            raise RuntimeError("System inspection is already running.")
        self.pending_roles = dict(roles)
        self.phase = InspectionPhase.PENDING

    def begin(self) -> None:
        if self.phase is not InspectionPhase.PENDING:
            raise RuntimeError("System inspection is not pending.")
        self.phase = InspectionPhase.RUNNING

    def complete(
        self,
        suggestions: dict[str, SpeciesRoleSuggestion],
        role_sources: dict[str, str],
    ) -> None:
        if self.phase is not InspectionPhase.RUNNING:
            raise RuntimeError("System inspection is not running.")
        self.suggestions = dict(suggestions)
        self.role_sources = dict(role_sources)
        self.phase = InspectionPhase.READY

    def set_pending_roles(self, roles: dict[str, str]) -> None:
        self.pending_roles = dict(roles)

    def edit_role(self, species: str, source: str | None) -> None:
        if source is None:
            self.role_sources.pop(species, None)
            return
        self.role_sources[species] = source

    def apply_suggestions(self, species: set[str], roles: dict[str, str]) -> None:
        self.role_sources.update(dict.fromkeys(species, "suggestion_batch"))
        self.set_pending_roles(roles)

    def cancel_roles(self, source: str) -> set[str]:
        species = {
            name
            for name, current_source in self.role_sources.items()
            if current_source == source
        }
        for name in species:
            self.role_sources.pop(name, None)
        return species

    def fail(self) -> None:
        if self.phase is not InspectionPhase.RUNNING:
            raise RuntimeError("System inspection is not running.")
        self.phase = InspectionPhase.FAILED

    def reset(self) -> None:
        self.phase = InspectionPhase.EMPTY
        self.pending_roles.clear()
        self.suggestions.clear()
        self.role_sources.clear()
