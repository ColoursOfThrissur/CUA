"""Compatibility router export for autonomy endpoints."""

from api.rest.autonomy.agent_router import (
    GoalRequest,
    PlanApprovalRequest,
    achieve_goal,
    clear_session_memory,
    get_agent_status,
    get_execution_state,
    get_learned_patterns,
    get_session_memory,
    get_strategic_memory_stats,
    pause_execution,
    resume_execution,
    router,
    set_agent_dependencies,
)

__all__ = [
    "GoalRequest",
    "PlanApprovalRequest",
    "achieve_goal",
    "clear_session_memory",
    "get_agent_status",
    "get_execution_state",
    "get_learned_patterns",
    "get_session_memory",
    "get_strategic_memory_stats",
    "pause_execution",
    "resume_execution",
    "router",
    "set_agent_dependencies",
]
