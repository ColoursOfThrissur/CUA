"""File-backed skill repository implementation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

from domain.entities.skill_models import SkillDefinition
from domain.repositories.skill_repository import ISkillRepository
from infrastructure.logging.logging_system import get_logger


class SkillFileStorage(ISkillRepository):
    """Loads skill definitions from the project `skills/` directory."""

    REQUIRED_FIELDS = {
        "name",
        "category",
        "description",
        "trigger_examples",
        "preferred_tools",
        "required_tools",
        "preferred_connectors",
        "input_types",
        "output_types",
        "verification_mode",
        "risk_level",
        "ui_renderer",
        "fallback_strategy",
    }

    def __init__(self, skills_dir: str = "skills"):
        self.skills_dir = Path(skills_dir)
        self.logger = get_logger("skill_repository")

    def load_all(self) -> Dict[str, SkillDefinition]:
        skills: Dict[str, SkillDefinition] = {}
        if not self.skills_dir.exists():
            self.logger.warning("skills_directory_missing", path=str(self.skills_dir))
            return skills

        for skill_dir in sorted(path for path in self.skills_dir.iterdir() if path.is_dir()):
            skill = self._load_skill(skill_dir)
            if skill:
                skills[skill.name] = skill
        return skills

    def get(self, name: str) -> Optional[SkillDefinition]:
        skills = self.load_all()
        return skills.get(name)

    def _load_skill(self, skill_dir: Path) -> Optional[SkillDefinition]:
        skill_json = skill_dir / "skill.json"
        skill_md = skill_dir / "SKILL.md"

        if not skill_json.exists() or not skill_md.exists():
            self.logger.warning(
                "invalid_skill_layout",
                skill_dir=str(skill_dir),
                skill_json_exists=skill_json.exists(),
                skill_md_exists=skill_md.exists(),
            )
            return None

        try:
            data = json.loads(skill_json.read_text(encoding="utf-8"))
        except Exception as exc:
            self.logger.error("skill_json_parse_failed", skill_dir=str(skill_dir), error=str(exc))
            return None

        missing = sorted(self.REQUIRED_FIELDS - set(data.keys()))
        if missing:
            self.logger.warning("skill_missing_fields", skill_dir=str(skill_dir), missing=missing)
            return None

        try:
            return SkillDefinition(
                name=str(data["name"]),
                category=str(data["category"]),
                description=str(data["description"]),
                trigger_examples=list(data["trigger_examples"]),
                preferred_tools=list(data["preferred_tools"]),
                required_tools=list(data["required_tools"]),
                preferred_connectors=list(data["preferred_connectors"]),
                input_types=list(data["input_types"]),
                output_types=list(data["output_types"]),
                verification_mode=str(data["verification_mode"]),
                risk_level=str(data["risk_level"]),
                ui_renderer=str(data["ui_renderer"]),
                fallback_strategy=str(data["fallback_strategy"]),
                skill_dir=str(skill_dir),
                instructions_path=str(skill_md),
            )
        except Exception as exc:
            self.logger.error("skill_normalization_failed", skill_dir=str(skill_dir), error=str(exc))
            return None
