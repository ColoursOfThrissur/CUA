"""
Task Manager API Endpoints
"""
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/tasks", tags=["task-manager"])

# Global task manager instance (set from server)
task_manager_instance = None

def set_task_manager(tm):
    global task_manager_instance
    task_manager_instance = tm

@router.get("/active")
async def get_active_task():
    """Get currently executing parent task with subtasks"""
    if not task_manager_instance:
        return {"active": False, "parent_task": None}
    
    return task_manager_instance.get_status()

@router.get("/history")
async def get_task_history(limit: int = 20):
    """Get completed parent tasks"""
    if not task_manager_instance:
        return {"history": []}
    
    return {"history": task_manager_instance.get_history(limit)}

@router.post("/{parent_id}/abort")
async def abort_task(parent_id: str):
    """Abort parent task and rollback staging"""
    if not task_manager_instance:
        raise HTTPException(status_code=503, detail="Task manager not initialized")
    
    result = task_manager_instance.abort_parent_task(parent_id)
    
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result["error"])
    
    return result

@router.get("/{parent_id}/staging")
async def get_staging_preview(parent_id: str):
    """Preview staged changes before commit"""
    if not task_manager_instance:
        raise HTTPException(status_code=503, detail="Task manager not initialized")
    
    staging = task_manager_instance.staging_areas.get(parent_id)
    if not staging:
        raise HTTPException(status_code=404, detail="Staging area not found")
    
    return staging.get_preview()
