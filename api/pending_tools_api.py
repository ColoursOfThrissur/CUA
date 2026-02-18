"""
Pending Tools API Endpoints
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/pending-tools", tags=["pending-tools"])

# Global instances (set from server)
pending_tools_manager = None
tool_registrar = None

def set_pending_tools_manager(ptm):
    global pending_tools_manager
    pending_tools_manager = ptm

def set_tool_registrar(tr):
    global tool_registrar
    tool_registrar = tr

class RejectRequest(BaseModel):
    reason: Optional[str] = ""

@router.get("/list")
async def get_pending_tools():
    """Get all pending tools awaiting approval"""
    if not pending_tools_manager:
        return {"pending_tools": []}
    
    return {"pending_tools": pending_tools_manager.get_pending_list()}

@router.get("/{tool_id}")
async def get_tool_details(tool_id: str):
    """Get detailed info about pending tool"""
    if not pending_tools_manager:
        raise HTTPException(status_code=503, detail="Manager not initialized")
    
    tool = pending_tools_manager.get_tool(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    
    return tool

@router.post("/{tool_id}/approve")
async def approve_tool(tool_id: str):
    """Approve and activate tool"""
    if not pending_tools_manager or not tool_registrar:
        raise HTTPException(status_code=503, detail="System not initialized")
    
    # Get tool metadata
    tool = pending_tools_manager.get_tool(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    
    # Register tool dynamically
    tool_file = tool.get('tool_file')
    if not tool_file:
        raise HTTPException(status_code=400, detail="No tool file specified")
    
    reg_result = tool_registrar.register_new_tool(tool_file)
    
    if not reg_result['success']:
        return {
            "success": False,
            "error": f"Registration failed: {reg_result['error']}"
        }
    
    # Mark as approved
    approve_result = pending_tools_manager.approve_tool(tool_id)
    
    return {
        "success": True,
        "tool_name": reg_result['tool_name'],
        "capabilities": reg_result['capabilities'],
        "message": f"Tool '{reg_result['tool_name']}' activated successfully"
    }

@router.post("/{tool_id}/reject")
async def reject_tool(tool_id: str, request: RejectRequest):
    """Reject and remove pending tool"""
    if not pending_tools_manager:
        raise HTTPException(status_code=503, detail="Manager not initialized")
    
    result = pending_tools_manager.reject_tool(tool_id, request.reason)
    
    if not result['success']:
        raise HTTPException(status_code=404, detail=result['error'])
    
    return {"success": True, "message": "Tool rejected and removed"}

@router.get("/active/list")
async def get_active_tools():
    """Get list of currently active tools"""
    if not tool_registrar:
        return {"active_tools": []}
    
    return {"active_tools": tool_registrar.get_active_tools()}
