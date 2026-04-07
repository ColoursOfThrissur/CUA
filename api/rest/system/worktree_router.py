"""Worktree lifecycle API endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from application.services.worktree_handoff_service import WorktreeHandoffService
from application.services.worktree_policy_service import WorktreePolicyService
from application.services.worktree_task_service import WorktreeTaskService

router = APIRouter(prefix="/api/worktrees", tags=["worktrees"])


@router.get("/readiness")
async def get_worktree_readiness():
    service = WorktreeTaskService()
    return service.readiness.get_readiness()


@router.get("/list")
async def list_worktrees():
    result = WorktreeTaskService().list_worktrees()
    if not result["success"]:
        raise HTTPException(status_code=503, detail=result["reason"])
    return result


@router.get("/policy")
async def get_worktree_policy(goal: str = Query(default="")):
    service = WorktreeTaskService()
    return {
        "success": True,
        "policy": WorktreePolicyService().recommend(
            goal=goal,
            readiness=service.readiness.get_readiness(),
        ),
    }


@router.get("/cleanup")
async def preview_worktree_cleanup():
    result = WorktreeTaskService().cleanup_worktrees(apply=False)
    if not result["success"]:
        raise HTTPException(status_code=503, detail=result.get("reason", "Worktree cleanup preview unavailable"))
    return result


@router.post("/cleanup")
async def apply_worktree_cleanup():
    result = WorktreeTaskService().cleanup_worktrees(apply=True)
    if not result["success"]:
        raise HTTPException(status_code=503, detail=result.get("reason", "Worktree cleanup unavailable"))
    return result


@router.get("/handoffs")
async def list_worktree_handoffs():
    result = WorktreeHandoffService().list_handoffs()
    if not result["success"]:
        raise HTTPException(status_code=503, detail=result.get("reason", "Worktree handoff inspection unavailable"))
    return result


@router.post("/{label}/handoff")
async def assign_worktree_handoff(
    label: str,
    owner: str = Query(...),
    purpose: str = Query(default="bounded handoff"),
    session_id: str = Query(default=""),
    task_id: str = Query(default=""),
):
    try:
        result = WorktreeHandoffService().assign_handoff(
            label,
            owner=owner,
            purpose=purpose,
            session_id=session_id or None,
            task_id=task_id or None,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    if not result["success"]:
        raise HTTPException(status_code=409, detail=result["reason"])
    return result


@router.delete("/{label}/handoff")
async def release_worktree_handoff(label: str, note: str = Query(default="")):
    try:
        result = WorktreeHandoffService().release_handoff(label, note=note)
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    if not result["success"]:
        raise HTTPException(status_code=409, detail=result["reason"])
    return result


@router.post("/{label}")
async def create_worktree(label: str):
    result = WorktreeTaskService().create_worktree(label)
    if not result["success"]:
        raise HTTPException(status_code=409, detail=result["reason"])
    return result


@router.delete("/{label}")
async def delete_worktree(label: str, force: bool = False):
    result = WorktreeTaskService().remove_worktree(label, force=force)
    if not result["success"]:
        status_code = 409 if result.get("error") in {"dirty_worktree", "not_found"} else 503
        raise HTTPException(status_code=status_code, detail=result["reason"])
    return result
