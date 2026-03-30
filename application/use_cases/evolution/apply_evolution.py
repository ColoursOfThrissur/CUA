"""Use case for approving and applying a pending evolution."""

from __future__ import annotations

from typing import Optional

from application.managers.pending_evolutions_manager import PendingEvolutionsManager


class ApplyEvolutionUseCase:
    """Application-facing wrapper around pending evolution approval."""

    def __init__(self, pending_manager: Optional[PendingEvolutionsManager] = None):
        self.pending_manager = pending_manager or PendingEvolutionsManager()

    def execute(self, tool_name: str) -> bool:
        return self.pending_manager.approve_evolution(tool_name)


def apply_evolution(tool_name: str, pending_manager: Optional[PendingEvolutionsManager] = None) -> bool:
    """Compatibility helper for older callers expecting a function API."""

    return ApplyEvolutionUseCase(pending_manager).execute(tool_name)


__all__ = ["ApplyEvolutionUseCase", "apply_evolution"]
