"""
Self-Improvement Loop API Endpoints
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

router = APIRouter(prefix="/improvement", tags=["self-improvement"])

# Global loop instance (initialized in main server)
loop_instance = None

def set_loop_instance(loop):
    global loop_instance
    loop_instance = loop
    print(f"[DEBUG] Loop instance set: {loop is not None}")

class StartLoopRequest(BaseModel):
    max_iterations: Optional[int] = 10
    custom_prompt: Optional[str] = None
    dry_run: Optional[bool] = False

class StopLoopRequest(BaseModel):
    mode: str = "graceful"

class ApprovalRequest(BaseModel):
    proposal_id: str
    approved: bool

class ImportPlanRequest(BaseModel):
    data: dict

@router.post("/start")
async def start_loop(request: StartLoopRequest):
    if not loop_instance:
        raise HTTPException(status_code=503, detail="Loop not initialized")
    
    loop_instance.custom_focus = request.custom_prompt if request.custom_prompt else None
    loop_instance.dry_run = request.dry_run if request.dry_run else False
    
    result = await loop_instance.start_loop()
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return result

@router.post("/stop")
async def stop_loop(request: StopLoopRequest):
    if not loop_instance:
        raise HTTPException(status_code=503, detail="Loop not initialized")
    
    result = await loop_instance.stop_loop(request.mode)
    return result

@router.post("/approve")
async def approve_proposal(request: ApprovalRequest):
    if not loop_instance:
        raise HTTPException(status_code=503, detail="Loop not initialized")
    
    # Use lock to prevent concurrent approval conflicts
    async with loop_instance.approval_lock:
        if request.approved:
            success = loop_instance.approve_proposal(request.proposal_id)
        else:
            success = loop_instance.reject_proposal(request.proposal_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Proposal not found or already processed")
    
    return {"success": True, "proposal_id": request.proposal_id, "approved": request.approved}

@router.get("/status")
async def get_status():
    """Get current loop status - returns default if not initialized"""
    if not loop_instance:
        return {
            "status": "not_initialized",
            "running": False,
            "iteration": 0,
            "maxIterations": 10,
            "logs": [],
            "dry_run": False,
            "preview_count": 0,
            "pending_approvals": {},
            "message": "Self-improvement loop not initialized. Check server logs."
        }
    
    status = loop_instance.get_status()
    status['pending_approvals'] = loop_instance.pending_approvals
    return status

@router.post("/clear-logs")
async def clear_logs():
    if not loop_instance:
        raise HTTPException(status_code=503, detail="Loop not initialized")
    
    loop_instance.logs = []
    return {"success": True}

@router.get("/previews")
async def get_previews():
    if not loop_instance:
        return {"previews": []}
    return {"previews": loop_instance.preview_proposals}

@router.get("/history")
async def get_history(limit: int = 50):
    if not loop_instance:
        return {"history": []}
    history = loop_instance.plan_history.get_history(limit)
    return {"history": history}

@router.get("/analytics")
async def get_analytics(days: int = 30):
    if not loop_instance:
        return {
            "total_attempts": 0,
            "successful_attempts": 0,
            "success_rate": 0,
            "avg_duration_seconds": 0,
            "risk_distribution": {},
            "common_errors": [],
            "daily_trend": []
        }
    stats = loop_instance.analytics.get_stats(days)
    return stats

@router.get("/logs")
async def get_logs():
    if not loop_instance:
        return {"logs": []}
    return {"logs": loop_instance.logs}

@router.post("/export/{proposal_id}")
async def export_proposal(proposal_id: str):
    """Export proposal as JSON for sharing"""
    if not loop_instance:
        raise HTTPException(status_code=503, detail="Loop not initialized")
    
    proposal = None
    for preview in loop_instance.preview_proposals:
        if f"proposal_{preview['iteration']:03d}" == proposal_id:
            proposal = preview
            break
    
    if not proposal and proposal_id in loop_instance.pending_approvals:
        proposal = loop_instance.pending_approvals[proposal_id]
    
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    
    return {
        "proposal_id": proposal_id,
        "exported_at": datetime.now().isoformat(),
        "data": proposal
    }

@router.post("/import")
async def import_plan(request: ImportPlanRequest):
    """Import and validate exported plan"""
    if not loop_instance:
        raise HTTPException(status_code=503, detail="Loop not initialized")
    
    try:
        if 'proposal' not in request.data:
            raise HTTPException(status_code=400, detail="Invalid plan format")
        
        proposal = request.data['proposal']
        required = ['description', 'files_changed', 'patch']
        
        for field in required:
            if field not in proposal:
                raise HTTPException(status_code=400, detail=f"Missing {field}")
        
        # Validate files against protected files
        from core.immutable_brain_stem import BrainStem
        for file_path in proposal['files_changed']:
            result = BrainStem.validate_path(file_path)
            if not result.is_valid:
                raise HTTPException(status_code=400, detail=f"Invalid file path: {result.reason}")
        
        # Validate patch format
        patch = proposal.get('patch', '')
        if not patch or not ('---' in patch or '+++' in patch):
            raise HTTPException(status_code=400, detail="Invalid patch format")
        
        proposal_id = f"imported_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        loop_instance.pending_approvals[proposal_id] = {
            "proposal": proposal,
            "risk_score": request.data.get('risk_score'),
            "approved": None
        }
        
        loop_instance.add_log("info", f"Plan imported: {proposal['description']}", proposal_id)
        
        return {
            "success": True,
            "proposal_id": proposal_id,
            "message": "Plan imported. Review and approve to execute."
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/history/{plan_id}")
async def get_plan_details(plan_id: str):
    """Get detailed plan information"""
    if not loop_instance:
        raise HTTPException(status_code=503, detail="Loop not initialized")
    
    plan = loop_instance.plan_history.get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    return plan

@router.post("/rollback/{plan_id}")
async def rollback_plan(plan_id: str):
    """Rollback to state before plan was applied"""
    if not loop_instance:
        raise HTTPException(status_code=503, detail="Loop not initialized")
    
    # Check if loop is running
    if loop_instance.state.status.value == "running":
        raise HTTPException(status_code=409, detail="Cannot rollback while loop is running. Stop the loop first.")
    
    plan = loop_instance.plan_history.get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    backup_id = plan.get('backup_id', '')
    if not backup_id:
        raise HTTPException(status_code=400, detail="No backup available for this plan")
    
    try:
        from updater.atomic_applier import AtomicApplier
        applier = AtomicApplier(repo_path=".")
        
        if backup_id.startswith('manual_backup_'):
            # Manual backup - find .bak file
            update_id = backup_id.replace('manual_backup_', '')
            from pathlib import Path
            backup_dir = Path("backups")
            
            # Find matching backup file
            backup_files = list(backup_dir.glob(f"*.{update_id}.bak"))
            if not backup_files:
                raise HTTPException(status_code=404, detail="Backup file not found")
            
            success = applier.rollback_manual_backup(backup_files[0].name)
        else:
            # Git-based backup
            update_id = backup_id.replace('backup_', '')
            success = applier.rollback(update_id)
        
        if success:
            loop_instance.add_log("info", f"Rolled back plan {plan_id}")
            return {"success": True, "message": f"Rolled back to {backup_id}"}
        else:
            raise HTTPException(status_code=500, detail="Rollback failed")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rollback error: {str(e)}")
