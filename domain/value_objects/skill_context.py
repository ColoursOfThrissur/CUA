from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, Optional

from domain.entities.skill_models import SkillDefinition, SkillPlanningContext


def build_skill_planning_context(skill: SkillDefinition) -> SkillPlanningContext:
    instructions = Path(skill.instructions_path).read_text(encoding="utf-8")
    summary_lines = []
    for raw_line in instructions.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        summary_lines.append(line)
        if len(summary_lines) >= 8:
            break

    constraints = []
    if skill.required_tools:
        constraints.append(f"Required tools: {', '.join(skill.required_tools)}")
    if skill.preferred_tools:
        constraints.append(f"Preferred tools: {', '.join(skill.preferred_tools)}")
    if skill.output_types:
        constraints.append(f"Expected outputs: {', '.join(skill.output_types)}")

    return SkillPlanningContext(
        skill_name=skill.name,
        category=skill.category,
        instructions_summary=" ".join(summary_lines),
        preferred_tools=skill.preferred_tools,
        required_tools=skill.required_tools,
        verification_mode=skill.verification_mode,
        output_types=skill.output_types,
        ui_renderer=skill.ui_renderer,
        skill_constraints=constraints,
    )


def build_domain_catalog(skill_registry, tool_registry, selected_skill_name: Optional[str] = None) -> Dict[str, Any]:
    tool_details = {}
    for tool in getattr(tool_registry, "tools", []):
        capabilities = []
        for capability_name, capability in (tool.get_capabilities() or {}).items():
            capabilities.append(
                {
                    "name": capability_name,
                    "description": capability.description,
                    "parameters": [param.name for param in capability.parameters],
                }
            )
        tool_details[tool.__class__.__name__] = capabilities

    domains = []
    for skill in skill_registry.list_all():
        domain_tools = []
        referenced_tools = list(dict.fromkeys(skill.preferred_tools + skill.required_tools))
        for tool_name in referenced_tools:
            domain_tools.append(
                {
                    "name": tool_name,
                    "capabilities": tool_details.get(tool_name, []),
                }
            )

        domains.append(
            {
                "name": skill.category,
                "skill_name": skill.name,
                "description": skill.description,
                "preferred_tools": skill.preferred_tools,
                "required_tools": skill.required_tools,
                "output_types": skill.output_types,
                "ui_renderer": skill.ui_renderer,
                "selected": skill.name == selected_skill_name,
                "tools": domain_tools,
            }
        )

    return {
        "selected_skill": selected_skill_name,
        "domains": domains,
    }
