"""Bounded local desktop execution policy for computer-use plans.

This policy does not replace global planning. It only activates for
desktop-bounded `computer_automation` plans and can:
- stop early when answer-quality evidence is already available
- insert short local recovery steps when the target app loses focus
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from domain.entities.task import TaskStep
from tools.computer_use.task_state import infer_task_state
from tools.computer_use.visual_policy import build_visual_policy_plan


DESKTOP_POLICY_PROFILES = {
    "desktop_ui_navigation",
    "desktop_ui_extraction",
    "desktop_ui_detail_lookup",
}
DESKTOP_POLICY_TOOLS = {
    "SystemControlTool",
    "InputAutomationTool",
    "ScreenPerceptionTool",
}


def _ctx_value(skill_context: Any, key: str, default: Any = None) -> Any:
    if isinstance(skill_context, dict):
        return skill_context.get(key, default)
    if hasattr(skill_context, key):
        value = getattr(skill_context, key)
        if value is not None:
            return value
    planning_hints = getattr(skill_context, "planning_hints", None) or {}
    if key in planning_hints:
        return planning_hints.get(key, default)
    validation_rules = getattr(skill_context, "validation_rules", None) or {}
    return validation_rules.get(key, default)


@dataclass
class LocalDesktopPolicyDecision:
    action: str = "continue"  # continue | complete | recover
    reason: str = ""
    recovery_steps: List[TaskStep] = field(default_factory=list)


class LocalDesktopPolicy:
    """Execution-time optimizer for simple desktop-only plans."""

    def __init__(self, *, goal: str, planning_profile: str, target_app: str):
        self.goal = str(goal or "").strip()
        self.planning_profile = str(planning_profile or "").strip().lower()
        self.target_app = str(target_app or "").strip().lower()
        self._recovery_counter = 0

    @classmethod
    def build(cls, *, plan, skill_context: Any) -> Optional["LocalDesktopPolicy"]:
        skill_name = str(_ctx_value(skill_context, "skill_name", "") or "").strip().lower()
        planning_profile = str(_ctx_value(skill_context, "planning_profile", "") or "").strip().lower()
        if skill_name != "computer_automation" or planning_profile not in DESKTOP_POLICY_PROFILES:
            return None

        tool_names = {step.tool_name for step in getattr(plan, "steps", []) or []}
        if not tool_names or not tool_names.issubset(DESKTOP_POLICY_TOOLS):
            return None

        task_state = infer_task_state(str(getattr(plan, "goal", "") or ""), {})
        return cls(
            goal=str(getattr(plan, "goal", "") or ""),
            planning_profile=planning_profile,
            target_app=task_state.target_app,
        )

    def assess_wave(
        self,
        *,
        wave_results: Dict[str, Any],
        remaining_steps: List[TaskStep],
        state: Any,
    ) -> LocalDesktopPolicyDecision:
        if self._has_satisfied_goal_evidence(wave_results):
            return LocalDesktopPolicyDecision(
                action="complete",
                reason="Bounded desktop policy found answer-quality evidence; skipping redundant remaining desktop steps.",
            )

        recovery_steps = self._build_recovery_steps(remaining_steps=remaining_steps, state=state)
        if recovery_steps:
            return LocalDesktopPolicyDecision(
                action="recover",
                reason="Bounded desktop policy detected app focus/state drift; inserting a short local recovery sequence.",
                recovery_steps=recovery_steps,
            )

        return LocalDesktopPolicyDecision()

    def _has_satisfied_goal_evidence(self, wave_results: Dict[str, Any]) -> bool:
        goal_lower = self.goal.lower()
        for result in wave_results.values():
            output = getattr(result, "output", None)
            if not isinstance(output, dict):
                continue
            if output.get("success") is False:
                continue
            if not self._output_matches_target_app(output):
                continue

            if self.planning_profile == "desktop_ui_detail_lookup":
                if output.get("answer_ready") is True:
                    return True
                if (
                    output.get("requested_field")
                    and output.get("field_value")
                    and not output.get("ambiguous", False)
                ):
                    return True
                if (
                    output.get("target")
                    and output.get("summary")
                    and any(word in goal_lower for word in ("find", "read", "show", "how many", "hours", "status", "detail"))
                ):
                    return bool(output.get("field_value")) and not output.get("ambiguous", False)

            if self.planning_profile == "desktop_ui_extraction":
                if output.get("items") or output.get("structured_rows"):
                    return True
                if output.get("summary") and not output.get("ambiguous", False):
                    return True

        return False

    def _output_matches_target_app(self, output: Dict[str, Any]) -> bool:
        if not self.target_app:
            return True
        if output.get("grounding", {}).get("target_app") and output.get("grounded") is False:
            return False
        active_window_title = str(output.get("active_window_title", "") or "").lower()
        if self.target_app in active_window_title:
            return True
        visual_state = output.get("visual_state") or {}
        if isinstance(visual_state, dict) and visual_state.get("target_app_active"):
            return True
        return False

    def _build_recovery_steps(self, *, remaining_steps: List[TaskStep], state: Any) -> List[TaskStep]:
        if not self.target_app or not remaining_steps:
            return []
        if not any(step.tool_name in {"InputAutomationTool", "ScreenPerceptionTool"} for step in remaining_steps):
            return []

        context = self._build_policy_context(state)
        if not context.get("active_window") and not context.get("visual_state"):
            return []
        task_state = infer_task_state(self.goal, context)
        if task_state.current_app_active:
            return []

        policy_plan = build_visual_policy_plan(
            self.goal,
            {
                "task_state": task_state.to_dict(),
                "ui_elements": context.get("ui_elements", []),
                "completed_steps": context.get("completed_steps", []),
            },
        )
        if not policy_plan:
            return []

        recovery_steps: List[TaskStep] = []
        previous_step_id: Optional[str] = None
        for index, action in enumerate(policy_plan, start=1):
            tool_name = str(action.get("tool", "") or "").strip()
            operation = str(action.get("operation", "") or "").strip()
            parameters = dict(action.get("parameters") or {})
            if not tool_name or not operation:
                continue

            self._recovery_counter += 1
            step_id = f"desktop_policy_recovery_{self._recovery_counter}"
            recovery_steps.append(
                TaskStep(
                    step_id=step_id,
                    description=f"Local desktop recovery: {tool_name}.{operation}",
                    tool_name=tool_name,
                    operation=operation,
                    parameters=parameters,
                    dependencies=[previous_step_id] if previous_step_id else [],
                    expected_output="Desktop state is corrected for the next action.",
                    domain="computer",
                    retry_on_failure=False,
                    max_retries=1,
                    retry_policy={"max_attempts": 1, "supervisor_retries": 1},
                )
            )
            previous_step_id = step_id

        return recovery_steps

    def _build_policy_context(self, state: Any) -> Dict[str, Any]:
        latest_output: Dict[str, Any] = {}
        step_results = list((getattr(state, "step_results", {}) or {}).values())
        for result in reversed(step_results):
            output = getattr(result, "output", None)
            if isinstance(output, dict):
                latest_output = output
                break

        visual_state = latest_output.get("visual_state") if isinstance(latest_output, dict) else {}
        active_window = str((latest_output or {}).get("active_window_title", "") or "")
        ui_elements = []
        for label in (visual_state or {}).get("visible_targets", []) or []:
            label_text = str(label).strip()
            if label_text:
                ui_elements.append({"label": label_text, "type": "text"})

        completed_steps = []
        registry = getattr(state, "state_registry", None)
        if registry is not None and hasattr(registry, "build_completed_steps"):
            completed_steps = registry.build_completed_steps()

        return {
            "active_window": active_window,
            "visual_state": visual_state or {},
            "ui_elements": ui_elements,
            "completed_steps": completed_steps,
        }
