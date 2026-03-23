from __future__ import annotations

from typing import Dict, List, Optional

from core.skills.loader import SkillLoader
from core.skills.models import SkillDefinition


class SkillRegistry:
    """In-memory registry of skill definitions."""

    def __init__(self, loader: Optional[SkillLoader] = None):
        self.loader = loader or SkillLoader()
        self._skills: Dict[str, SkillDefinition] = {}

    def load_all(self) -> Dict[str, SkillDefinition]:
        self._skills = self.loader.load_all()
        return dict(self._skills)

    def refresh(self) -> Dict[str, SkillDefinition]:
        return self.load_all()

    def get(self, name: str) -> Optional[SkillDefinition]:
        return self._skills.get(name)

    def list_all(self) -> List[SkillDefinition]:
        return list(self._skills.values())

    def list_by_category(self, category: str) -> List[SkillDefinition]:
        return [skill for skill in self._skills.values() if skill.category == category]

    def to_routing_context(self) -> List[dict]:
        return [
            {
                "name": skill.name,
                "category": skill.category,
                "description": skill.description,
                "trigger_examples": skill.trigger_examples,
                "preferred_tools": skill.preferred_tools,
                "output_types": skill.output_types,
            }
            for skill in self.list_all()
        ]
