"""Domain contract for loading skill definitions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Optional

from domain.entities.skill_models import SkillDefinition


class ISkillRepository(ABC):
    """Abstraction for skill-definition persistence."""

    @abstractmethod
    def load_all(self) -> Dict[str, SkillDefinition]:
        """Load all known skills keyed by skill name."""

    @abstractmethod
    def get(self, name: str) -> Optional[SkillDefinition]:
        """Load a single skill definition by name if available."""
