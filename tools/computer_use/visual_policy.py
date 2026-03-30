"""
Deterministic visual policy for computer-use tasks.

This layer sits between grounded perception and LLM planning. It prefers
visible UI targets first, and only falls back to system/window APIs when
there is no reliable visual target to act on.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from tools.computer_use.task_state import extract_target_app


INSPECTION_WORDS = ("see", "what", "list", "show", "check", "find", "inspect", "read")


def build_visual_policy_plan(intent: str, context: Optional[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
    """Return a short grounded plan when state is clear enough to avoid LLM planning.
    
    IMPORTANT: This is GENERIC policy, not app-specific. No hardcoded app logic.
    Only handles:
    - Launch app if not visible
    - Focus app if visible but not active
    - Analyze screen if inspection requested
    
    Everything else (navigation, clicking specific buttons) → LLM planner
    """
    lowered = (intent or "").lower().strip()
    context = context or {}

    target_app = extract_target_app(lowered)
    if not target_app and not any(word in lowered for word in INSPECTION_WORDS):
        return None

    task_state = context.get("task_state", {}) or {}
    ui_elements = context.get("ui_elements", []) or []
    completed_steps = context.get("completed_steps", []) or []

    wants_inspection = any(word in lowered for word in INSPECTION_WORDS)
    app_visible = bool(task_state.get("current_app_visible"))
    app_active = bool(task_state.get("current_app_active"))

    app_launched = any(
        step.get("tool") == "SystemControlTool"
        and step.get("operation") == "launch_application"
        and target_app in str((step.get("parameters") or {}).get("name", "")).lower()
        for step in completed_steps
    )

    app_target = _best_visible_target(target_app, ui_elements, []) if target_app else None

    # RULE 1: App not visible → Launch it
    if target_app and not app_visible:
        if not app_launched:
            plan: List[Dict[str, Any]] = [
                {
                    "tool": "SystemControlTool",
                    "operation": "launch_application",
                    "parameters": {"name": target_app},
                }
            ]
            # If user wants to inspect, add observation step
            if wants_inspection:
                plan.append(
                {
                    "tool": "ScreenPerceptionTool",
                    "operation": "infer_visual_state",
                    "parameters": {"target_app": target_app},
                }
            )
            return plan
        # Already launched but not visible yet → observe
        return [
            {
                "tool": "ScreenPerceptionTool",
                "operation": "infer_visual_state",
                "parameters": {"target_app": target_app},
            }
        ]

    # RULE 2: App visible but not active → Focus it
    if target_app and app_visible and not app_active:
        if app_target:
            return [
                {
                    "tool": "InputAutomationTool",
                    "operation": "smart_click",
                    "parameters": {"target": app_target},
                }
            ]
        return [
            {
                "tool": "SystemControlTool",
                "operation": "focus_window",
                "parameters": {"title": target_app},
            }
        ]


    # RULE 4: UI elements available → Let LLM handle navigation
    # Don't try to be smart about clicking specific buttons - that's the LLM's job
    if ui_elements:
        return None  # LLM planner will handle it

    # RULE 5: No clear action → Let LLM decide
    return None


def _best_visible_target(target: str, ui_elements: List[Dict[str, Any]], visible_targets: Optional[List[str]] = None) -> Optional[str]:
    """Find best matching UI element for a target (used only for app window matching)."""
    lowered_target = (target or "").lower().strip()
    if not lowered_target:
        return None

    best_label: Optional[str] = None
    best_score = 0.0

    for elem in ui_elements:
        label = str(elem.get("label") or elem.get("text") or "").strip()
        if not label:
            continue
        lowered_label = label.lower()
        
        # Exact match = best
        if lowered_label == lowered_target:
            return label
        
        # Substring match
        score = 0.0
        if lowered_target in lowered_label:
            score = 2.0
        elif lowered_label in lowered_target:
            score = 1.5
        
        if score == 0:
            continue

        # Prefer windows and buttons
        elem_type = str(elem.get("type") or "").lower()
        if elem_type in {"window"}:
            score += 1.0
        elif elem_type in {"button", "icon"}:
            score += 0.5
        
        score += float(elem.get("confidence") or 0.0)

        if score > best_score:
            best_score = score
            best_label = label

    return best_label
