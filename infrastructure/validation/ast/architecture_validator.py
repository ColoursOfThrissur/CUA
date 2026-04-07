"""Architecture contract helpers for skill/artifact-aware tool generation."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def normalize_artifact_types(value: Any) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        value = [value]
    result: List[str] = []
    for item in value:
        text = str(item).strip()
        if text and text not in result:
            result.append(text)
    return result


def enrich_tool_spec_with_skill_context(spec: Dict[str, Any], skill_context: Optional[dict]) -> Dict[str, Any]:
    if not skill_context:
        spec.setdefault("artifact_types", normalize_artifact_types(spec.get("outputs", [])))
        return spec

    target_skill = str(skill_context.get("target_skill") or "").strip()
    target_category = str(skill_context.get("target_category") or "").strip()
    verification_mode = str(skill_context.get("verification_mode") or "").strip()
    ui_renderer = str(skill_context.get("ui_renderer") or "").strip()
    output_types = normalize_artifact_types(skill_context.get("output_types"))

    if target_skill and (not verification_mode or not ui_renderer or not output_types):
        try:
            from application.services.skill_registry import SkillRegistry

            skill_registry = SkillRegistry()
            skill_registry.load_all()
            skill = skill_registry.get(target_skill)
            if skill:
                if not target_category:
                    target_category = skill.category
                if not verification_mode:
                    verification_mode = skill.verification_mode
                if not ui_renderer:
                    ui_renderer = skill.ui_renderer
                if not output_types:
                    output_types = list(skill.output_types)
        except Exception:
            pass

    if target_skill:
        spec["target_skill"] = target_skill
    if target_category:
        spec["target_category"] = target_category
        if str(spec.get("domain") or "").strip() in {"", "general"}:
            spec["domain"] = target_category
    if verification_mode and not spec.get("verification_mode"):
        spec["verification_mode"] = verification_mode
    if ui_renderer and not spec.get("ui_renderer"):
        spec["ui_renderer"] = ui_renderer

    artifact_types = normalize_artifact_types(spec.get("artifact_types"))
    if not artifact_types:
        artifact_types = normalize_artifact_types(spec.get("outputs", []))
    if not artifact_types and output_types:
        artifact_types = output_types
    spec["artifact_types"] = artifact_types

    return spec


def validate_skill_aware_architecture_contract(spec: Dict[str, Any]) -> Tuple[bool, str]:
    target_skill = str(spec.get("target_skill") or "").strip()
    target_category = str(spec.get("target_category") or "").strip()
    verification_mode = str(spec.get("verification_mode") or "").strip()
    ui_renderer = str(spec.get("ui_renderer") or "").strip()
    artifact_types = normalize_artifact_types(spec.get("artifact_types"))

    if target_skill or target_category:
        if not target_skill:
            return False, "Architecture contract requires target_skill for skill-aware tools"
        if not target_category:
            return False, "Architecture contract requires target_category for skill-aware tools"
        if not verification_mode:
            return False, "Architecture contract requires verification_mode for skill-aware tools"
        if not ui_renderer:
            return False, "Architecture contract requires ui_renderer for skill-aware tools"
        if not artifact_types:
            return False, "Architecture contract requires artifact_types for skill-aware tools"
        
        # Validate service alignment with skill
        service_alignment_ok, service_error = validate_service_alignment(spec)
        if not service_alignment_ok:
            return False, service_error

    return True, ""


def validate_service_alignment(spec: Dict[str, Any]) -> Tuple[bool, str]:
    """Validate that tool's service usage aligns with skill constraints."""
    target_skill = str(spec.get("target_skill") or "").strip()
    if not target_skill:
        return True, ""

    try:
        from application.services.skill_registry import SkillRegistry
        skill_registry = SkillRegistry()
        skill_registry.load_all()
        skill = skill_registry.get(target_skill)
        if not skill:
            return True, ""
    except Exception:
        return True, ""

    tool_code = spec.get("code", "")
    if not tool_code:
        return True, ""

    # Only enforce source_backed verification for tools that explicitly fetch/retrieve sources.
    # Processing tools (summarizers, extractors) in the same skill don't need to store sources.
    if skill.verification_mode == "source_backed":
        fetcher_keywords = ("fetch_url", "search_web", "self.services.http", "self.services.browser")
        is_fetcher = any(kw in tool_code for kw in fetcher_keywords)
        if is_fetcher and "self.services.storage" not in tool_code:
            return False, "Source-backed verification requires storage service to persist sources"

    return True, ""


def infer_skill_contract_for_tool(tool_name: str) -> Dict[str, Any]:
    try:
        from application.services.skill_registry import SkillRegistry

        skill_registry = SkillRegistry()
        skill_registry.load_all()
        for skill in skill_registry.list_all():
            known_tools = list(skill.preferred_tools) + list(skill.required_tools)
            if tool_name in known_tools:
                return {
                    "target_skill": skill.name,
                    "target_category": skill.category,
                    "verification_mode": skill.verification_mode,
                    "ui_renderer": skill.ui_renderer,
                    "output_types": list(skill.output_types),
                }
    except Exception:
        pass
    return {}
