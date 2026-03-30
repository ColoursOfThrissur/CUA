"""Skills API - expose loaded skill definitions."""
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/skills", tags=["skills"])

_skill_registry = None


def set_skill_registry(skill_registry):
    global _skill_registry
    _skill_registry = skill_registry


@router.get("/list")
async def list_skills():
    if _skill_registry is None:
        raise HTTPException(status_code=503, detail="Skill registry not initialized")

    skills = _skill_registry.list_all()
    categories = {}
    serialized = []
    for skill in skills:
        categories.setdefault(skill.category, 0)
        categories[skill.category] += 1
        serialized.append(
            {
                "name": skill.name,
                "category": skill.category,
                "description": skill.description,
                "trigger_examples": skill.trigger_examples,
                "preferred_tools": skill.preferred_tools,
                "required_tools": skill.required_tools,
                "output_types": skill.output_types,
                "verification_mode": skill.verification_mode,
                "risk_level": skill.risk_level,
                "ui_renderer": skill.ui_renderer,
                "fallback_strategy": skill.fallback_strategy,
            }
        )

    return {"count": len(serialized), "categories": categories, "skills": serialized}


@router.get("/{skill_name}")
async def get_skill(skill_name: str):
    if _skill_registry is None:
        raise HTTPException(status_code=503, detail="Skill registry not initialized")

    skill = _skill_registry.get(skill_name)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    return {
        "name": skill.name,
        "category": skill.category,
        "description": skill.description,
        "trigger_examples": skill.trigger_examples,
        "preferred_tools": skill.preferred_tools,
        "required_tools": skill.required_tools,
        "preferred_connectors": skill.preferred_connectors,
        "input_types": skill.input_types,
        "output_types": skill.output_types,
        "verification_mode": skill.verification_mode,
        "risk_level": skill.risk_level,
        "ui_renderer": skill.ui_renderer,
        "fallback_strategy": skill.fallback_strategy,
        "skill_dir": skill.skill_dir,
        "instructions_path": skill.instructions_path,
    }
