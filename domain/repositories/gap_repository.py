"""Domain contract for capability-gap persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, List, Optional


class IGapRepository(ABC):
    """Abstraction over stored capability gaps."""

    @abstractmethod
    def record_gap(self, gap: Any) -> None:
        """Persist or update a detected capability gap."""

    @abstractmethod
    def get_gap(self, capability: str) -> Optional[Any]:
        """Return a stored gap by capability name."""

    @abstractmethod
    def list_actionable(self) -> List[Any]:
        """Return actionable unresolved gaps."""
