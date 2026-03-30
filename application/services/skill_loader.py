from __future__ import annotations

from typing import Dict

from domain.entities.skill_models import SkillDefinition
from domain.repositories.skill_repository import ISkillRepository
from infrastructure.persistence.file_storage.skill_file_storage import SkillFileStorage


class SkillLoader:
    """Application-facing skill loading service backed by a repository."""

    def __init__(self, repository: ISkillRepository | None = None, skills_dir: str = "skills"):
        self.repository = repository or SkillFileStorage(skills_dir=skills_dir)

    def load_all(self) -> Dict[str, SkillDefinition]:
        return self.repository.load_all()
