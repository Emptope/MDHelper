"""System inspection state for the desktop GUI."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

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
    provenance: dict[str, Any] = field(default_factory=dict)

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
        provenance: dict[str, Any],
    ) -> None:
        if self.phase is not InspectionPhase.RUNNING:
            raise RuntimeError("System inspection is not running.")
        self.suggestions = dict(suggestions)
        self.provenance = dict(provenance)
        self.phase = InspectionPhase.READY

    def set_pending_roles(self, roles: dict[str, str]) -> None:
        self.pending_roles = dict(roles)

    def edit_role(self, species: str, decision: object | None) -> None:
        if decision is None:
            self.provenance.pop(species, None)
            return
        self.provenance[species] = decision

    def apply_roles(
        self,
        decisions: Mapping[str, object],
        roles: dict[str, str],
    ) -> None:
        self.provenance.update(decisions)
        self.set_pending_roles(roles)

    def cancel_roles(self, source: str) -> set[str]:
        species = {
            name
            for name, decision in self.provenance.items()
            if isinstance(decision, dict) and decision.get("source") == source
        }
        for name in species:
            self.provenance.pop(name, None)
        return species

    def fail(self) -> None:
        if self.phase is not InspectionPhase.RUNNING:
            raise RuntimeError("System inspection is not running.")
        self.phase = InspectionPhase.FAILED

    def reset(self) -> None:
        self.phase = InspectionPhase.EMPTY
        self.pending_roles.clear()
        self.suggestions.clear()
        self.provenance.clear()
