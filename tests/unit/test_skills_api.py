import asyncio

from api.skills_api import get_skill, list_skills, set_skill_registry
from core.skills import SkillRegistry


def _load_registry():
    registry = SkillRegistry()
    registry.load_all()
    set_skill_registry(registry)
    return registry


def test_list_skills_returns_loaded_skill_catalog():
    _load_registry()

    response = asyncio.run(list_skills())

    assert response["count"] >= 3
    assert "web_research" in {skill["name"] for skill in response["skills"]}
    assert response["categories"]["web"] >= 1


def test_get_skill_returns_full_skill_definition():
    _load_registry()

    response = asyncio.run(get_skill("computer_automation"))

    assert response["name"] == "computer_automation"
    assert response["category"] == "computer"
    assert "FilesystemTool" in response["preferred_tools"]
