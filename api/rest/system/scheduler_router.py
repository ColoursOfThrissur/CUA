"""
Scheduler API - Manage scheduled improvements
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/schedule", tags=["scheduler"])

scheduler_instance = None

def set_scheduler(sched):
    global scheduler_instance
    scheduler_instance = sched

class ScheduleRequest(BaseModel):
    schedule_id: str
    cron: str  # "daily:02:00" or "hourly" or "weekly:monday:03:00"
    max_iterations: Optional[int] = 5
    dry_run: Optional[bool] = False

@router.get("/list")
async def list_schedules():
    """Get all schedules"""
    if not scheduler_instance:
        raise HTTPException(status_code=500, detail="Scheduler not initialized")
    
    return {"schedules": scheduler_instance.get_schedules()}

@router.post("/create")
async def create_schedule(request: ScheduleRequest):
    """Create new schedule"""
    if not scheduler_instance:
        raise HTTPException(status_code=500, detail="Scheduler not initialized")
    
    schedule = scheduler_instance.add_schedule(
        request.schedule_id,
        request.cron,
        request.max_iterations,
        request.dry_run
    )
    
    return {
        "success": True,
        "schedule_id": schedule.schedule_id,
        "message": f"Schedule created: {request.cron}"
    }

@router.delete("/{schedule_id}")
async def delete_schedule(schedule_id: str):
    """Delete schedule"""
    if not scheduler_instance:
        raise HTTPException(status_code=500, detail="Scheduler not initialized")
    
    success = scheduler_instance.remove_schedule(schedule_id)
    
    if success:
        return {"success": True, "message": "Schedule deleted"}
    else:
        raise HTTPException(status_code=404, detail="Schedule not found")

@router.post("/{schedule_id}/enable")
async def enable_schedule(schedule_id: str, enabled: bool = True):
    """Enable/disable schedule"""
    if not scheduler_instance:
        raise HTTPException(status_code=500, detail="Scheduler not initialized")
    
    success = scheduler_instance.enable_schedule(schedule_id, enabled)
    
    if success:
        return {
            "success": True,
            "message": f"Schedule {'enabled' if enabled else 'disabled'}"
        }
    else:
        raise HTTPException(status_code=404, detail="Schedule not found")
