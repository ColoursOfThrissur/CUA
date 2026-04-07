"""Create Plan Use Case - Orchestrates plan creation."""
import logging
import re
from typing import Optional, Dict
from domain.entities.task import ExecutionPlan
from domain.repositories.repositories import ToolRepository, MemoryRepository
from infrastructure.llm.llm_gateway import LLMGateway
from infrastructure.llm.prompt_builder import PlanningPromptBuilder
from infrastructure.validation.plan_validator import PlanValidator

logger = logging.getLogger(__name__)


class CreatePlanUseCase:
    """Use case for creating execution plans."""
    
    def __init__(
        self,
        llm_gateway: LLMGateway,
        tool_repo: ToolRepository,
        memory_repo: MemoryRepository,
        prompt_builder: PlanningPromptBuilder,
        plan_validator: PlanValidator
    ):
        self._llm = llm_gateway
        self._tools = tool_repo
        self._memory = memory_repo
        self._prompts = prompt_builder
        self._validator = plan_validator
    
    def execute(self, user_goal: str, context: Optional[Dict] = None) -> ExecutionPlan:
        """Create execution plan from user goal."""
        logger.info(f"[PLANNER] Planning task: '{user_goal[:80]}'")
        
        # Get skill context
        skill_context = (context or {}).get("skill_context", {})
        skill_name = skill_context.get("skill_name", "")
        planning_mode = str(skill_context.get("planning_mode", "") or "").strip().lower()
        preferred_tools = set(skill_context.get("preferred_tools", []))
        excluded_tools = set((context or {}).get("excluded_tools", []))
        include_past_plans = bool(skill_context.get("include_past_plans", True))
        include_memory_context = bool(skill_context.get("include_memory_context", True))
        
        # Get available tools
        available_tools = self._tools.get_capabilities(preferred_tools or None)
        if excluded_tools:
            available_tools = {
                tool_name: capabilities
                for tool_name, capabilities in available_tools.items()
                if tool_name not in excluded_tools
            }
        
        # Retrieve similar past plans
        plan_top_k = 5 if planning_mode == "deep" else 3
        past_plans = self._memory.find_similar_plans(user_goal, skill_name, top_k=plan_top_k) if include_past_plans else []
        
        # Get unified memory context
        unified_context = self._memory.search_context(user_goal, skill_name) if include_memory_context else ""
        planning_feedback = (context or {}).get("planning_failure_feedback")
        if planning_feedback:
            unified_context = f"{unified_context}\n\nPlanner feedback: {planning_feedback}".strip()

        # Build prompt
        prompt = self._prompts.build_planning_prompt(
            goal=user_goal,
            tools=available_tools,
            skill_context=skill_context,
            past_plans=past_plans,
            unified_context=unified_context
        )
        
        # Get LLM response
        try:
            response = self._llm.generate_plan(prompt, temperature=0.3)
            
            if not response:
                raise RuntimeError("LLM returned no response")
            
            logger.info(f"[PLANNER] Raw response len={len(response)}")
            
            # Parse and validate
            plan_data = self._validator.parse_llm_response(response)
            plan = self._validator.validate(plan_data, user_goal)
            self._optimize_computer_use_plan(plan, user_goal, skill_context)
            self._enforce_desktop_extraction_requirements(plan, user_goal, skill_context)
            
            logger.info(f"[PLANNER] Plan ready: {len(plan.steps)} steps, complexity={plan.complexity}")
            return plan
            
        except Exception as e:
            logger.error(f"Planning failed: {e}")
            raise RuntimeError(f"Failed to create execution plan: {e}")

    def _optimize_computer_use_plan(
        self,
        plan: ExecutionPlan,
        user_goal: str,
        skill_context: Dict,
    ) -> None:
        """Trim redundant desktop perception and propagate app hints."""
        if (skill_context or {}).get("skill_name") != "computer_automation":
            return

        planning_profile = str((skill_context or {}).get("planning_profile", "") or "").strip().lower()
        current_app_hint = self._infer_app_hint(user_goal, plan)
        for step in plan.steps:
            if step.tool_name == "SystemControlTool":
                if step.operation == "launch_application":
                    current_app_hint = str(step.parameters.get("name", "")).strip().lower() or current_app_hint
                elif step.operation == "focus_window":
                    current_app_hint = str(step.parameters.get("title", "")).strip().lower() or current_app_hint

            if current_app_hint and step.tool_name == "InputAutomationTool" and step.operation == "smart_click":
                step.parameters.setdefault("target_app", current_app_hint)

            if current_app_hint and step.tool_name == "ScreenPerceptionTool" and step.operation in {
                "infer_visual_state",
                "get_comprehensive_state",
                "extract_text",
                "get_visible_text",
                "get_ui_text",
            }:
                step.parameters.setdefault("target_app", current_app_hint)

            if (
                step.tool_name == "ScreenPerceptionTool"
                and step.operation == "analyze_screen"
                and self._is_extraction_prompt(step.parameters.get("prompt"))
            ):
                step.operation = "extract_text"
                step.parameters.setdefault("target_app", current_app_hint)

            if (
                planning_profile == "desktop_ui_detail_lookup"
                and step.tool_name == "ScreenPerceptionTool"
                and step.operation in {"extract_text", "get_visible_text", "get_ui_text", "analyze_screen"}
            ):
                step.operation = "extract_text"
                step.parameters["prompt"] = self._build_goal_focused_extraction_prompt(user_goal)
                if current_app_hint:
                    step.parameters.setdefault("target_app", current_app_hint)
                step.expected_output = "The requested on-screen detail is extracted for the named target item."
                step.description = "Extract only the specific on-screen detail needed to answer the user's request."

        removable_ids = set()
        dependency_counts = self._count_dependencies(plan)
        steps = plan.steps
        for index, step in enumerate(steps):
            if step.tool_name != "ScreenPerceptionTool" or step.operation != "infer_visual_state":
                continue

            next_step = steps[index + 1] if index + 1 < len(steps) else None
            if not next_step:
                continue
            if next_step.tool_name != "InputAutomationTool" or next_step.operation != "smart_click":
                continue

            removable_ids.add(step.step_id)
            prior_capture = steps[index - 1] if index > 0 else None
            if (
                prior_capture
                and prior_capture.tool_name == "ScreenPerceptionTool"
                and prior_capture.operation == "capture_screen"
                and dependency_counts.get(prior_capture.step_id, 0) <= 1
            ):
                removable_ids.add(prior_capture.step_id)

        if removable_ids:
            self._remove_steps(plan, removable_ids)

    def _build_goal_focused_extraction_prompt(self, user_goal: str) -> str:
        """Convert a broad planner extraction step into a goal-shaped prompt."""
        request = str(user_goal or "").strip()
        lines = [
            f"Extract only the specific detail needed to answer this request: {request}",
            "Prefer the named item and its explicitly labeled value or field.",
        ]
        target_hint = self._infer_named_target_hint(request)
        if target_hint:
            lines.append(f'Named target item: "{target_hint}"')
        field_hint = self._infer_requested_field_hint(request)
        if field_hint:
            lines.append(f"Requested field hint: {field_hint}")
        lines.append("Do not return unrelated visible items unless they are needed to disambiguate the answer.")
        return "\n".join(lines)

    def _infer_requested_field_hint(self, user_goal: str) -> str:
        """Infer the requested field so extractors can stay structured and label-bound."""
        goal_lower = str(user_goal or "").strip().lower()
        if any(word in goal_lower for word in ("playtime", "hours played", "hours of game", "hrs", "hours")):
            return "playtime in hours"
        if "status" in goal_lower:
            return "current status"
        if any(phrase in goal_lower for phrase in ("how many", "count")):
            return "count"
        if any(word in goal_lower for word in ("find", "read", "show", "extract")):
            return "specific requested detail"
        return ""

    def _infer_named_target_hint(self, user_goal: str) -> str:
        """Extract a likely target item name from the goal without app-specific hardcoding."""
        text = str(user_goal or "").strip()
        if not text:
            return ""

        for pattern in (
            r'["\']([^"\']{3,})["\']',
            r"\bnamed target item:\s*['\"]?([^\"\n]+?)['\"]?(?:\n|$)",
        ):
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                candidate = self._clean_named_target_hint(match.group(1))
                if candidate:
                    return candidate

        lower_text = text.lower()
        for pattern in (
            r"\b(?:for|in)\s+([a-z0-9' :\-]{3,}?)(?:\.\.|[.?!]|,\s| in library\b| on steam\b| from\b|$)",
            r"\bgame\s+([a-z0-9' :\-]{3,}?)(?:\.\.|[.?!]|,\s| in library\b| on steam\b| from\b|$)",
        ):
            match = re.search(pattern, lower_text, flags=re.IGNORECASE)
            if match:
                candidate = self._clean_named_target_hint(match.group(1))
                if candidate:
                    return candidate
        return ""

    def _clean_named_target_hint(self, candidate: str) -> str:
        """Trim filler words and punctuation from inferred target hints."""
        cleaned = str(candidate or "").strip(" \t\r\n.,:;!?\"'")
        cleaned = re.sub(r"^(the\s+)?(game|title)\s+", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if len(cleaned) < 3:
            return ""
        return cleaned

    def _is_extraction_prompt(self, prompt: Optional[str]) -> bool:
        """Detect analyze_screen prompts that are really extraction requests."""
        lower = str(prompt or "").strip().lower()
        if not lower:
            return False
        return any(word in lower for word in ("extract", "list", "visible game titles", "visible titles", "read the text"))

    def _enforce_desktop_extraction_requirements(
        self,
        plan: ExecutionPlan,
        user_goal: str,
        skill_context: Dict,
    ) -> None:
        """Reject desktop plans that only observe the screen for extraction-style requests."""
        goal_lower = (user_goal or "").lower()
        skill_name = (skill_context or {}).get("skill_name", "")

        if skill_name != "computer_automation":
            return

        if not any(word in goal_lower for word in ("list", "show", "find", "count", "extract", "read")):
            return

        step_tools = {step.tool_name for step in plan.steps}
        step_ops = {step.operation for step in plan.steps}
        extraction_ops = {
            "smart_click",
            "click",
            "type_text",
            "press_key",
            "hotkey",
            "get_visible_text",
            "get_ui_text",
            "extract_text",
            "read_text",
        }
        perception_only = step_tools.issubset({"ScreenPerceptionTool", "SystemControlTool"}) and not (step_ops & extraction_ops)

        if perception_only:
            raise RuntimeError(
                "Desktop extraction request planned as perception-only flow. "
                "Plan must include an interaction or explicit text/data extraction step."
            )

    def _infer_app_hint(self, user_goal: str, plan: ExecutionPlan) -> str:
        """Best-effort app hint for desktop steps."""
        goal_lower = (user_goal or "").lower()
        for app_name in ("steam", "notepad", "calculator", "chrome", "vscode", "code"):
            if app_name in goal_lower:
                return "vscode" if app_name == "code" else app_name

        for step in plan.steps:
            if step.tool_name == "SystemControlTool" and step.operation == "launch_application":
                name = str(step.parameters.get("name", "")).strip().lower()
                if name:
                    return name
        return ""

    def _count_dependencies(self, plan: ExecutionPlan) -> Dict[str, int]:
        """Count how many later steps depend on each step."""
        counts: Dict[str, int] = {}
        for step in plan.steps:
            for dep in step.dependencies:
                counts[dep] = counts.get(dep, 0) + 1
        return counts

    def _remove_steps(self, plan: ExecutionPlan, removable_ids: set[str]) -> None:
        """Remove steps and reconnect downstream dependencies."""
        if not removable_ids:
            return

        dependency_map = {
            step.step_id: list(step.dependencies)
            for step in plan.steps
        }
        kept_steps = []
        for step in plan.steps:
            if step.step_id in removable_ids:
                continue

            rebuilt_dependencies = []
            seen = set()
            stack = list(step.dependencies)
            while stack:
                dep = stack.pop(0)
                if dep in seen:
                    continue
                seen.add(dep)
                if dep in removable_ids:
                    stack = list(dependency_map.get(dep, [])) + stack
                    continue
                rebuilt_dependencies.append(dep)
            step.dependencies = rebuilt_dependencies
            kept_steps.append(step)

        plan.steps = kept_steps
