"""Skill selection and context building for chat requests."""
from typing import Dict, List, Optional
from pathlib import Path


def select_skill_for_message(message: str, skill_reg, skill_sel, llm, reg) -> Dict:
    """Select appropriate skill for user message."""
    if not skill_reg or not skill_sel:
        return {
            "matched": False, "skill_name": None, "category": None, "confidence": 0.0,
            "reason": "skill_system_unavailable", "fallback_mode": "direct_tool_routing",
            "candidate_skills": []
        }
    try:
        result = skill_sel.select_skill(message, skill_reg, llm)
        return {
            "matched": bool(result.matched), "skill_name": result.skill_name,
            "category": result.category, "confidence": result.confidence,
            "reason": getattr(result, "reason", ""),
            "fallback_mode": getattr(result, "fallback_mode", None),
            "candidate_skills": getattr(result, "candidate_skills", []),
            "planning_context": getattr(result, "planning_context", None),
        }
    except Exception as e:
        print(f"[WARN] Skill selection failed: {e}")
        return {
            "matched": False, "skill_name": None, "category": None, "confidence": 0.0,
            "reason": f"error:{e}", "fallback_mode": "direct_tool_routing",
            "candidate_skills": []
        }


def build_planner_context(skill_selection: Dict, skill_reg=None) -> Optional[Dict]:
    """Build execution context from skill selection."""
    if not skill_selection.get("matched"):
        return None

    skill_name = skill_selection.get("skill_name")
    base = {
        "skill_name": skill_name,
        "category": skill_selection.get("category"),
        "confidence": skill_selection.get("confidence"),
        "planning_context": skill_selection.get("planning_context"),
    }

    if skill_reg and skill_name:
        skill_def = skill_reg.get(skill_name)
        if skill_def:
            preferred_tools = list(skill_def.preferred_tools or [])
            if skill_name == "computer_automation":
                preferred_tools = [tool for tool in preferred_tools if tool != "ComputerUseController"]
                for tool_name in ("SystemControlTool", "InputAutomationTool", "ScreenPerceptionTool"):
                    if tool_name not in preferred_tools:
                        preferred_tools.append(tool_name)
            instructions_summary = ""
            try:
                md = Path(skill_def.instructions_path).read_text(encoding="utf-8")
                lines = [l.strip() for l in md.splitlines() if l.strip() and not l.startswith("#")]
                instructions_summary = " ".join(lines[:3])[:300]
            except Exception:
                pass
            base["skill_context"] = {
                "skill_name": skill_name,
                "category": skill_def.category,
                "preferred_tools": preferred_tools,
                "required_tools": skill_def.required_tools,
                "verification_mode": skill_def.verification_mode,
                "output_types": skill_def.output_types,
                "ui_renderer": skill_def.ui_renderer,
                "instructions_summary": instructions_summary,
                "skill_constraints": [],
            }
    return base


def selected_ui_renderer(skill_selection: Dict) -> str:
    """Get UI renderer for skill."""
    skill_name = (skill_selection or {}).get("skill_name") or ""
    renderers = {
        "web_research": "web_results",
        "browser_automation": "screenshot",
        "data_operations": "table",
        "code_workspace": "code",
        "knowledge_management": "markdown"
    }
    return renderers.get(skill_name, "default")


def selected_output_types(skill_selection: Dict) -> List[str]:
    """Get expected output types for skill."""
    skill_name = (skill_selection or {}).get("skill_name") or ""
    output_map = {
        "web_research": ["text", "url", "summary"],
        "browser_automation": ["screenshot", "text"],
        "data_operations": ["json", "table"],
        "code_workspace": ["code", "text"],
        "knowledge_management": ["text", "markdown"],
        "computer_automation": ["text", "file"],
    }
    return output_map.get(skill_name, [])
