"""
Pending Libraries API - Approve library installations
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/libraries", tags=["libraries"])

# Global instance
libraries_manager = None

def set_libraries_manager(manager):
    global libraries_manager
    libraries_manager = manager

class ApprovalRequest(BaseModel):
    reason: Optional[str] = None

@router.get("/pending")
async def get_pending_libraries():
    """Get all pending library approvals"""
    if not libraries_manager:
        raise HTTPException(status_code=500, detail="Libraries manager not initialized")
    
    return {"pending_libraries": libraries_manager.get_pending()}

@router.post("/{lib_id}/approve")
async def approve_library(lib_id: str):
    """Approve and install library"""
    if not libraries_manager:
        raise HTTPException(status_code=500, detail="Libraries manager not initialized")
    
    # Check if already approved (in case of server reload)
    pending = libraries_manager.get_pending()
    if not any(p["id"] == lib_id for p in pending):
        # Check if it was already approved
        if lib_id in libraries_manager.pending:
            lib_data = libraries_manager.pending[lib_id]
            if lib_data["status"] == "approved":
                return {"success": True, "library": lib_data["library"], "already_installed": True}
        return {"success": False, "error": "Library not found or already processed"}
    
    result = libraries_manager.approve(lib_id)
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Approval failed"))
    
    return result

@router.post("/{lib_id}/reject")
async def reject_library(lib_id: str, request: ApprovalRequest):
    """Reject library installation"""
    if not libraries_manager:
        raise HTTPException(status_code=500, detail="Libraries manager not initialized")
    
    result = libraries_manager.reject(lib_id, request.reason or "User rejected")
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Rejection failed"))
    
    return result
