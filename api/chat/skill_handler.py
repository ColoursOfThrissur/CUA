"""Skill selection and context building for chat requests."""
from typing import Dict, List, Optional
from pathlib import Path


_DOMAIN_HINTS = {"auto", "computer", "web", "code", "research", "finance"}


def _normalize_domain_hint(domain_hint: Optional[str]) -> str:
    value = str(domain_hint or "").strip().lower()
    return value if value in _DOMAIN_HINTS else ""


def _ordered_subset(items: List[str], allowed: List[str]) -> List[str]:
    allowed_set = set(allowed)
    subset = [item for item in items if item in allowed_set]
    for item in allowed:
        if item not in subset:
            subset.append(item)
    return subset


def _infer_planning_profile(skill_name: str, user_request: str, domain_hint: str = "") -> str:
    request = str(user_request or "").strip().lower()
    if skill_name == "computer_automation":
        shell_terms = {"shell", "powershell", "cmd", "command", "terminal", "python", "script", "bash"}
        file_terms = {"file", "files", "folder", "folders", "directory", "path", "json", "copy", "move", "delete", "read", "write"}
        benchmark_terms = {"benchmark", "benchmarks", "performance", "suite", "case", "latency"}
        detail_terms = {"playtime", "hours", "hrs", "on record", "details", "detail", "stat", "stats"}
        ui_terms = {"steam", "window", "screen", "visible", "title", "text", "library", "click", "open", "launch", "focus"}
        extraction_terms = {"find", "show", "count", "extract", "read", "list", "how many"}

        if any(term in request for term in benchmark_terms):
            return "benchmarking"
        if any(term in request for term in shell_terms):
            return "shell_execution"
        if any(term in request for term in file_terms):
            return "filesystem_local"
        if any(term in request for term in detail_terms) and any(term in request for term in ui_terms):
            return "desktop_ui_detail_lookup"
        if any(term in request for term in extraction_terms) and any(term in request for term in ui_terms):
            return "desktop_ui_extraction"
        if any(term in request for term in ("open", "launch", "start", "focus", "click", "type", "press", "switch")):
            return "desktop_ui_navigation"
        if domain_hint == "computer":
            return "system_control"
        return "system_control"

    if skill_name == "browser_automation":
        if any(term in request for term in ("form", "fill", "submit", "login", "sign in")):
            return "form_fill"
        if any(term in request for term in ("extract", "summarize", "read", "scrape")):
            return "page_extraction"
        return "simple_navigation"

    if skill_name == "code_workspace":
        if any(term in request for term in ("test", "pytest", "run tests")):
            return "test_run"
        if any(term in request for term in ("refactor", "cleanup", "restructure")):
            return "refactor"
        if any(term in request for term in ("analyze", "review", "repo", "repository")):
            return "repo_analysis"
        return "file_edit"

    return ""


def _refine_preferred_tools(skill_name: str, preferred_tools: List[str], planning_profile: str) -> List[str]:
    preferred = list(preferred_tools or [])
    profile_tools = {
        ("computer_automation", "desktop_ui_navigation"): [
            "SystemControlTool",
            "InputAutomationTool",
            "ScreenPerceptionTool",
        ],
        ("computer_automation", "desktop_ui_extraction"): [
            "SystemControlTool",
            "InputAutomationTool",
            "ScreenPerceptionTool",
        ],
        ("computer_automation", "desktop_ui_detail_lookup"): [
            "SystemControlTool",
            "InputAutomationTool",
            "ScreenPerceptionTool",
        ],
        ("computer_automation", "system_control"): [
            "SystemControlTool",
            "InputAutomationTool",
            "ScreenPerceptionTool",
        ],
        ("computer_automation", "filesystem_local"): [
            "FilesystemTool",
            "ShellTool",
        ],
        ("computer_automation", "shell_execution"): [
            "ShellTool",
            "FilesystemTool",
        ],
        ("computer_automation", "benchmarking"): [
            "BenchmarkRunnerTool",
            "ShellTool",
            "FilesystemTool",
        ],
    }
    narrowed = profile_tools.get((skill_name, planning_profile))
    if not narrowed:
        return preferred
    return _ordered_subset(preferred, narrowed)


def _profile_context_flags(skill_name: str, planning_profile: str, user_request: str) -> Dict[str, bool]:
    request = str(user_request or "").strip().lower()
    is_retry_like = any(term in request for term in ("again", "retry", "continue", "previous", "last time"))

    if skill_name == "computer_automation" and planning_profile in {
        "desktop_ui_navigation",
        "desktop_ui_extraction",
        "desktop_ui_detail_lookup",
        "system_control",
    }:
        return {
            "include_past_plans": is_retry_like,
            "include_memory_context": is_retry_like,
            "include_previous_context": is_retry_like,
            "include_adaptive_rules": planning_profile == "desktop_ui_detail_lookup",
            "use_compact_schema": True,
            "include_context_summarizer": False,
        }

    return {
        "include_past_plans": True,
        "include_memory_context": True,
        "include_previous_context": True,
        "include_adaptive_rules": True,
        "use_compact_schema": False,
        "include_context_summarizer": False,
    }


def _profile_guidance(skill_name: str, planning_profile: str) -> List[str]:
    profile_rules = {
        ("computer_automation", "desktop_ui_navigation"): [
            "Use the minimum direct UI steps needed to reach the requested app state.",
            "Prefer smart_click or focused input over broad exploratory perception.",
        ],
        ("computer_automation", "desktop_ui_extraction"): [
            "Navigate to the requested view first, then extract only the requested visible text or items.",
            "Avoid extra verification passes unless the first extraction is ambiguous.",
        ],
        ("computer_automation", "desktop_ui_detail_lookup"): [
            "Navigate to the target item first, then run a targeted extraction for the requested detail.",
            "Prefer labeled evidence over inferred values when extracting a specific stat or field.",
            "Stop planning after answer-quality evidence is likely to be available.",
        ],
        ("computer_automation", "filesystem_local"): [
            "Prefer direct filesystem operations over screen-driven workflows.",
        ],
        ("computer_automation", "shell_execution"): [
            "Prefer ShellTool for command execution and keep file helpers as secondary support.",
        ],
        ("computer_automation", "benchmarking"): [
            "Keep benchmark planning inside benchmark and shell tools only unless the request explicitly needs UI interaction.",
        ],
    }
    return profile_rules.get((skill_name, planning_profile), [])


def select_skill_for_message(message: str, skill_reg, skill_sel, llm, reg, domain_hint: Optional[str] = None) -> Dict:
    """Select appropriate skill for user message."""
    normalized_domain_hint = _normalize_domain_hint(domain_hint)
    if not skill_reg or not skill_sel:
        return {
            "matched": False, "skill_name": None, "category": None, "confidence": 0.0,
            "reason": "skill_system_unavailable", "fallback_mode": "direct_tool_routing",
            "candidate_skills": [], "domain_hint": normalized_domain_hint,
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
            "domain_hint": normalized_domain_hint,
        }
    except Exception as e:
        print(f"[WARN] Skill selection failed: {e}")
        return {
            "matched": False, "skill_name": None, "category": None, "confidence": 0.0,
            "reason": f"error:{e}", "fallback_mode": "direct_tool_routing",
            "candidate_skills": [], "domain_hint": normalized_domain_hint,
        }


def build_planner_context(skill_selection: Dict, skill_reg=None, user_request: str = "", domain_hint: Optional[str] = None) -> Optional[Dict]:
    """Build execution context from skill selection."""
    if not skill_selection.get("matched"):
        return None

    skill_name = skill_selection.get("skill_name")
    normalized_domain_hint = _normalize_domain_hint(domain_hint or skill_selection.get("domain_hint"))
    planning_profile = _infer_planning_profile(skill_name, user_request, normalized_domain_hint)
    base = {
        "skill_name": skill_name,
        "category": skill_selection.get("category"),
        "confidence": skill_selection.get("confidence"),
        "planning_context": skill_selection.get("planning_context"),
        "domain_hint": normalized_domain_hint,
        "planning_profile": planning_profile,
    }

    if skill_reg and skill_name:
        skill_def = skill_reg.get(skill_name)
        if skill_def:
            preferred_tools = list(skill_def.preferred_tools or [])
            if skill_name == "computer_automation":
                for tool_name in ("SystemControlTool", "InputAutomationTool", "ScreenPerceptionTool"):
                    if tool_name not in preferred_tools:
                        preferred_tools.append(tool_name)
            preferred_tools = _refine_preferred_tools(skill_name, preferred_tools, planning_profile)
            instructions_summary = ""
            try:
                md = Path(skill_def.instructions_path).read_text(encoding="utf-8")
                lines = [l.strip() for l in md.splitlines() if l.strip() and not l.startswith("#")]
                instructions_summary = " ".join(lines[:3])[:300]
            except Exception:
                pass
            metadata = skill_def.metadata or {}
            skill_constraints = [
                str(item).strip()
                for item in (metadata.get("skill_constraints") or [])
                if str(item).strip()
            ]
            workflow_guidance = [
                str(item).strip()
                for item in (metadata.get("workflow_guidance") or [])
                if str(item).strip()
            ]
            profile_flags = _profile_context_flags(skill_name, planning_profile, user_request)
            profile_guidance = _profile_guidance(skill_name, planning_profile)
            planning_hints = {
                "vision_mode": bool(metadata.get("vision_mode", False)),
                "screenshot_at_each_step": bool(metadata.get("screenshot_at_each_step", False)),
                "observe_act_verify_loop": bool(metadata.get("observe_act_verify_loop", False)),
                "failure_categories": [
                    str(item).strip()
                    for item in (metadata.get("failure_categories") or [])
                    if str(item).strip()
                ],
                "workflow_guidance": workflow_guidance,
                "planning_profile": planning_profile,
            }
            base["skill_context"] = {
                "skill_name": skill_name,
                "category": skill_def.category,
                "domain_hint": normalized_domain_hint,
                "planning_profile": planning_profile,
                "preferred_tools": preferred_tools,
                "required_tools": skill_def.required_tools,
                "verification_mode": skill_def.verification_mode,
                "output_types": skill_def.output_types,
                "ui_renderer": skill_def.ui_renderer,
                "instructions_summary": instructions_summary,
                "skill_constraints": skill_constraints,
                "workflow_guidance": workflow_guidance,
                "profile_guidance": profile_guidance,
                "planning_hints": planning_hints,
                **profile_flags,
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
