"""
Update API - Endpoints for managing updates
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import os

router = APIRouter(prefix="/updates", tags=["updates"])

# Initialize orchestrator
from updater.orchestrator import UpdateOrchestrator
orchestrator = UpdateOrchestrator(os.getcwd())

class UpdateProposal(BaseModel):
    patch_content: str
    changed_files: List[str]
    diff_lines: int

class ApprovalRequest(BaseModel):
    update_id: str
    approver: str
    patch_content: str
    changed_files: List[str]

@router.post("/propose")
async def propose_update(proposal: UpdateProposal):
    """Propose a new update"""
    
    result = orchestrator.propose_update(
        patch_content=proposal.patch_content,
        changed_files=proposal.changed_files,
        diff_lines=proposal.diff_lines
    )
    
    return {
        "success": result.success,
        "update_id": result.update_id,
        "risk_level": result.risk_score.level.value,
        "risk_score": result.risk_score.score,
        "reasons": result.risk_score.reasons,
        "approval_status": result.approval_status,
        "test_passed": result.test_passed,
        "applied": result.applied,
        "error": result.error,
        "audit_entry_id": result.audit_entry_id
    }

@router.post("/approve")
async def approve_update(approval: ApprovalRequest):
    """Approve a pending update"""
    
    result = orchestrator.approve_pending(
        update_id=approval.update_id,
        approver=approval.approver,
        patch_content=approval.patch_content,
        changed_files=approval.changed_files
    )
    
    return {
        "success": result.success,
        "update_id": result.update_id,
        "approval_status": result.approval_status,
        "test_passed": result.test_passed,
        "applied": result.applied,
        "error": result.error
    }

@router.get("/pending")
async def get_pending():
    """Get pending approvals"""
    
    pending = orchestrator.get_pending_approvals()
    
    return {
        "pending_count": len(pending),
        "pending_updates": [
            {
                "update_id": p.update_id,
                "risk_level": p.risk_score.level.value,
                "risk_score": p.risk_score.score,
                "reasons": p.risk_score.reasons,
                "requested_at": p.requested_at.isoformat()
            }
            for p in pending
        ]
    }

@router.get("/audit")
async def get_audit(limit: int = 10):
    """Get recent audit entries"""
    
    entries = orchestrator.audit_logger.get_recent(limit)
    
    return {
        "entries": entries,
        "integrity_verified": orchestrator.verify_audit_integrity()
    }

@router.get("/backups")
async def list_backups():
    """List available backups"""
    
    backups = orchestrator.atomic_applier.list_backups()
    
    return {"backups": backups}

@router.post("/rollback/{update_id}")
async def rollback_update(update_id: str):
    """Rollback an update"""
    
    success = orchestrator.atomic_applier.rollback(update_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Backup not found")
    
    return {"success": True, "update_id": update_id}
