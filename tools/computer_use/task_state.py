"""
Task-state inference for computer-use workflows.

This keeps controller/planner decisions grounded in explicit app/view evidence
instead of broad natural-language summaries.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any, Dict, List


@dataclass
class ComputerTaskState:
    target_app: str = ""
    current_app_visible: bool = False
    current_app_active: bool = False
    active_window_app: str = ""
    current_view: str = "unknown"
    visible_targets: List[str] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def infer_task_state(intent: str, context: Dict[str, Any]) -> ComputerTaskState:
    lowered = (intent or "").lower()
    target_app = extract_target_app(lowered)
    state = ComputerTaskState(target_app=target_app)

    active_window = str(context.get("active_window", "")).lower()
    open_windows = [str(w).lower() for w in context.get("open_windows", [])]
    screen_summary = str(context.get("screen_summary", "")).lower()
    screen_analysis = str(context.get("screen_analysis", "")).lower()
    ui_elements = context.get("ui_elements", []) or []
    visual_state = context.get("visual_state", {}) or {}

    state.active_window_app = _infer_active_window_app(active_window)

    if target_app:
        state.current_app_active = target_app in active_window
        state.current_app_visible = state.current_app_active or any(target_app in w for w in open_windows)
        if state.current_app_active:
            state.evidence.append(f"active_window={target_app}")
        elif state.current_app_visible:
            state.evidence.append(f"open_windows contains {target_app}")

    if visual_state:
        state.current_app_visible = bool(visual_state.get("target_app_visible", state.current_app_visible))
        state.current_app_active = bool(visual_state.get("target_app_active", state.current_app_active))
        visual_view = str(visual_state.get("current_view", "")).strip().lower()
        if visual_view and visual_view != "unknown":
            state.current_view = visual_view
            state.evidence.append(f"visual_state current_view={visual_view}")
        for label in visual_state.get("visible_targets", []) or []:
            label = str(label).strip()
            if label and label not in state.visible_targets:
                state.visible_targets.append(label)

    for elem in ui_elements:
        label = str(elem.get("label") or elem.get("text") or "").strip()
        if label and label not in state.visible_targets:
            state.visible_targets.append(label)

    return state


def extract_target_app(intent: str) -> str:
    lowered = (intent or "").lower().strip()
    for name in ("steam", "notepad", "chrome", "edge", "firefox", "discord", "spotify", "vscode", "visual studio code"):
        if name in lowered:
            return "vscode" if name == "visual studio code" else name
    return ""


def _infer_active_window_app(active_window: str) -> str:
    """Extract app name from active window title (generic, no hardcoding)."""
    # Common app names that might appear in window titles
    common_apps = [
        "steam", "notepad", "chrome", "edge", "firefox", "discord", 
        "spotify", "vscode", "visual studio code", "slack", "teams",
        "outlook", "word", "excel", "powerpoint"
    ]
    
    for name in common_apps:
        if name in active_window:
            return "vscode" if name == "visual studio code" else name
    
    if "cua agent" in active_window:
        return "cua"
    
    return ""
