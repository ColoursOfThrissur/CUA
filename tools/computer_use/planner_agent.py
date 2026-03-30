"""
PlannerAgent - Intent to execution plan generation.

Responsibilities:
- Parse user intent
- Generate step-by-step execution plan
- Use skill registry for reusable workflows
- NO execution, NO verification
"""
import json
import logging
from typing import Dict, List, Any, Optional

from tools.computer_use.visual_policy import build_visual_policy_plan

logger = logging.getLogger(__name__)


class PlannerAgent:
    """Generates execution plans from user intents."""

    def __init__(self, llm_client, orchestrator=None):
        self.llm = llm_client
        self.orchestrator = orchestrator
        self.vision_cache = {}  # Cache vision summaries
        self.screen_hash = None  # Track screen changes
        self.last_plan_confidence = 0.0  # Track plan confidence for chunking
        self.plan_cache = {}  # Cache LLM-generated plans by intent hash
        
        # Get model manager for multi-model orchestration
        from shared.config.model_manager import get_model_manager
        self.model_manager = get_model_manager(llm_client._client if hasattr(llm_client, '_client') else llm_client)

    def generate_plan(self, intent: str, context: Optional[Dict] = None) -> Dict:
        """
        Generate execution plan from intent.
        
        Args:
            intent: Full user request with all details
            context: Environment context (screen state, failures, conversation_history, previous_tool_outputs)
        
        Returns:
        {
            "success": bool,
            "plan": [{"tool": str, "operation": str, "params": dict}],
            "intent": str,
            "strategy": str,
            "error": str (if failed)
        }
        """
        try:
            context = context or {}
            cache_key = self._build_cache_key(intent, context)
            if cache_key in self.plan_cache:
                return {"success": True, "plan": self.plan_cache[cache_key], "intent": intent, "strategy": "cached"}

            policy_plan: List[Dict[str, Any]] = build_visual_policy_plan(intent, context) or []
            plan: List[Dict[str, Any]] = []
            strategy = "visual_policy" if policy_plan else "fallback"

            # Main CUA planner is the primary authority. Visual policy acts as hint/fallback,
            # not as a second competing planner.
            if self.orchestrator and hasattr(self.orchestrator, 'main_planner'):
                planning_context = dict(context)
                excluded_tools = list(planning_context.get("excluded_tools") or [])
                if "ComputerUseController" not in excluded_tools:
                    excluded_tools.append("ComputerUseController")
                planning_context["excluded_tools"] = excluded_tools
                if policy_plan:
                    planning_context["computer_use_policy_hint"] = policy_plan[:3]
                execution_plan = self.orchestrator.main_planner.plan_task(intent, planning_context)
                main_plan = self._execution_plan_to_steps(execution_plan)
                if main_plan:
                    plan = main_plan
                    strategy = "main_planner_with_visual_hints" if policy_plan else "main_planner"

            if not plan:
                plan = policy_plan

            # Cache the plan
            self.plan_cache[cache_key] = plan

            return {
                "success": True,
                "plan": plan,
                "intent": intent,
                "strategy": strategy,
                "confidence": self.last_plan_confidence or 0.7,
            }
        except Exception as e:
            logger.error(f"Failed to generate plan: {e}")
            return {"success": False, "plan": [], "intent": intent, "strategy": "error", "error": str(e)}

    def _build_cache_key(self, intent: str, context: Dict[str, Any]) -> str:
        """Cache on intent plus salient UI context to avoid stale desktop plans."""
        relevant_context = {
            "active_window": context.get("active_window"),
            "screen_summary": context.get("screen_summary"),
            "screen_analysis": context.get("screen_analysis"),
            "task_state": context.get("task_state"),
            "ui_elements": context.get("ui_elements", [])[:8],
            "previous_failure": context.get("previous_failure"),
            "completed_steps": context.get("completed_steps", [])[-3:],
        }
        return json.dumps({"intent": intent, "context": relevant_context}, sort_keys=True, default=str)

    def _execution_plan_to_steps(self, execution_plan: Any) -> List[Dict[str, Any]]:
        """Normalize TaskPlanner ExecutionPlan output into controller step dictionaries."""
        steps: List[Dict[str, Any]] = []
        for step in getattr(execution_plan, "steps", []) or []:
            steps.append({
                "tool": getattr(step, "tool_name", ""),
                "operation": getattr(step, "operation", ""),
                "params": getattr(step, "parameters", {}) or {},
                "description": getattr(step, "description", ""),
                "expected_output": getattr(step, "expected_output", ""),
            })
        return steps

    def _merge_plans(self, primary: List[Dict[str, Any]], secondary: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Merge plan sources while preserving order and avoiding duplicate steps."""
        merged: List[Dict[str, Any]] = []
        seen = set()
        for step in (primary or []) + (secondary or []):
            key = (
                step.get("tool"),
                step.get("operation"),
                json.dumps(step.get("params", {}), sort_keys=True, default=str),
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(step)
        return merged

