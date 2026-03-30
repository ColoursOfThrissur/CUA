"""Compatibility helpers for plan optimization and replanning."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from application.use_cases.planning.task_planner import TaskPlanner
from domain.entities.task import TaskStep


class OptimizePlanUseCase:
    """Thin adapter that exposes plan optimization through the refactored planner."""

    def __init__(self, planner: TaskPlanner):
        self.planner = planner

    def execute(
        self,
        original_goal: str,
        remaining_steps: List[TaskStep],
        replan_context: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> List[TaskStep]:
        return self.planner.replan_remaining(original_goal, remaining_steps, replan_context, context)


def optimize_plan(
    planner: TaskPlanner,
    original_goal: str,
    remaining_steps: List[TaskStep],
    replan_context: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None,
) -> List[TaskStep]:
    """Compatibility function API for callers that expect a standalone use case."""

    return OptimizePlanUseCase(planner).execute(original_goal, remaining_steps, replan_context, context)


__all__ = ["TaskPlanner", "OptimizePlanUseCase", "optimize_plan"]
