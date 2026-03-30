"""Gap-repository implementation backed by the existing gap tracker."""

from __future__ import annotations

from typing import Any, List, Optional

from domain.repositories.gap_repository import IGapRepository
from domain.services.gap_tracker import GapTracker


class GapRepository(IGapRepository):
    """Compatibility persistence adapter for capability gaps."""

    def __init__(self, tracker: Optional[GapTracker] = None):
        self.tracker = tracker or GapTracker()

    def record_gap(self, gap: Any) -> None:
        self.tracker.record_gap(gap)

    def get_gap(self, capability: str) -> Optional[Any]:
        return self.tracker.gaps.get(capability)

    def list_actionable(self) -> List[Any]:
        return self.tracker.get_actionable_gaps()
