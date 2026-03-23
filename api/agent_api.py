"""API for autonomous agent operations."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

router = APIRouter()

_agent = None
_memory = None
_executor = None


def set_agent_dependencies(agent, memory, executor):
    """Set dependencies."""
    global _agent, _memory, _executor
    _agent = agent
    _memory = memory
    _executor = executor


class GoalRequest(BaseModel):
    goal: str
    success_criteria: List[str] = []
    max_iterations: int = 5
    require_approval: bool = False
    session_id: str


class PlanApprovalRequest(BaseModel):
    session_id: str
    execution_id: str
    approved: bool


@router.post("/agent/goal")
async def achieve_goal(request: GoalRequest):
    """Start autonomous goal achievement."""
    if not _agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    
    from core.autonomous_agent import AgentGoal
    
    goal = AgentGoal(
        goal_text=request.goal,
        success_criteria=request.success_criteria,
        max_iterations=request.max_iterations,
        require_approval=request.require_approval
    )
    
    try:
        result = _agent.achieve_goal(goal, request.session_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agent/status/{session_id}")
async def get_agent_status(session_id: str):
    """Get agent status for session."""
    if not _agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    
    status = _agent.get_status(session_id)
    return status


@router.get("/agent/execution/{execution_id}")
async def get_execution_state(execution_id: str):
    """Get execution state."""
    if not _executor:
        raise HTTPException(status_code=500, detail="Executor not initialized")
    
    state = _executor.get_execution_state(execution_id)
    
    if not state:
        raise HTTPException(status_code=404, detail="Execution not found")
    
    # Convert to dict for JSON response
    return {
        "execution_id": execution_id,
        "status": state.status,
        "goal": state.plan.goal,
        "current_step": state.current_step,
        "steps": [
            {
                "step_id": step.step_id,
                "description": step.description,
                "status": state.step_results[step.step_id].status.value,
                "output": state.step_results[step.step_id].output,
                "error": state.step_results[step.step_id].error,
                "execution_time": state.step_results[step.step_id].execution_time
            }
            for step in state.plan.steps
        ],
        "start_time": state.start_time,
        "end_time": state.end_time,
        "error": state.error
    }


@router.post("/agent/execution/{execution_id}/pause")
async def pause_execution(execution_id: str):
    """Pause active execution."""
    if not _executor:
        raise HTTPException(status_code=500, detail="Executor not initialized")
    
    success = _executor.pause_execution(execution_id)
    
    if not success:
        raise HTTPException(status_code=400, detail="Cannot pause execution")
    
    return {"success": True, "message": "Execution paused"}


@router.post("/agent/execution/{execution_id}/resume")
async def resume_execution(execution_id: str):
    """Resume paused execution."""
    if not _executor:
        raise HTTPException(status_code=500, detail="Executor not initialized")
    
    try:
        state = _executor.resume_execution(execution_id)
        return {
            "success": True,
            "status": state.status,
            "message": "Execution resumed"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/agent/memory/{session_id}")
async def get_session_memory(session_id: str, limit: int = 20):
    """Get conversation memory for session."""
    if not _memory:
        raise HTTPException(status_code=500, detail="Memory not initialized")
    
    context = _memory.get_session(session_id)
    
    if not context:
        raise HTTPException(status_code=404, detail="Session not found")
    
    messages = _memory.get_recent_messages(session_id, limit=limit)
    
    return {
        "session_id": session_id,
        "active_goal": context.active_goal,
        "messages": [
            {
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.timestamp
            }
            for msg in messages
        ],
        "execution_history": context.execution_history,
        "user_preferences": context.user_preferences
    }


@router.post("/agent/memory/{session_id}/clear")
async def clear_session_memory(session_id: str):
    """Clear session memory."""
    if not _memory:
        raise HTTPException(status_code=500, detail="Memory not initialized")
    
    _memory.clear_session(session_id)
    
    return {"success": True, "message": f"Session {session_id} cleared"}


@router.get("/agent/patterns/{pattern_type}")
async def get_learned_patterns(pattern_type: str, limit: int = 10):
    """Get learned patterns."""
    if not _memory:
        raise HTTPException(status_code=500, detail="Memory not initialized")
    
    patterns = _memory.get_patterns(pattern_type, limit=limit)
    
    return {
        "pattern_type": pattern_type,
        "count": len(patterns),
        "patterns": patterns
    }


@router.get("/agent/strategic-memory")
async def get_strategic_memory_stats():
    """Stats and top patterns from strategic memory."""
    from core.strategic_memory import get_strategic_memory
    sm = get_strategic_memory()
    stats = sm.get_stats()
    # Include top 10 records sorted by win_rate * success_count
    records = sorted(
        sm._records.values(),
        key=lambda r: r.win_rate() * r.success_count,
        reverse=True,
    )[:10]
    stats["top_patterns"] = [
        {
            "goal_sample": r.goal_sample,
            "skill_name": r.skill_name,
            "win_rate": round(r.win_rate(), 2),
            "success_count": r.success_count,
            "fail_count": r.fail_count,
            "avg_duration_s": r.avg_duration_s,
            "steps": r.steps,
        }
        for r in records
    ]
    return stats
