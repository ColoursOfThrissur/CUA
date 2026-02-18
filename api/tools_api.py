"""
Tools API - Sync tool capabilities
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict

router = APIRouter(prefix="/api/tools", tags=["tools"])

# Global instances
registry_manager = None
llm_client_instance = None

def set_registry_manager(manager):
    global registry_manager
    registry_manager = manager

def set_llm_client_for_sync(client):
    global llm_client_instance
    llm_client_instance = client

class SyncResponse(BaseModel):
    success: bool
    synced: list
    failed: list
    timestamp: str
    message: str

@router.post("/sync", response_model=SyncResponse)
async def sync_tool_capabilities():
    """Sync all tool capabilities using LLM analysis"""
    
    if not registry_manager:
        raise HTTPException(status_code=500, detail="Registry manager not initialized")
    
    if not llm_client_instance:
        raise HTTPException(status_code=500, detail="LLM client not available")
    
    try:
        # Run sync
        results = registry_manager.sync_all_tools(llm_client_instance)
        
        message = f"Synced {len(results['synced'])} tools"
        if results['failed']:
            message += f", {len(results['failed'])} failed"
        
        return SyncResponse(
            success=True,
            synced=results["synced"],
            failed=results["failed"],
            timestamp=results["timestamp"],
            message=message
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")

@router.get("/registry")
async def get_tool_registry():
    """Get current tool registry"""
    
    if not registry_manager:
        raise HTTPException(status_code=500, detail="Registry manager not initialized")
    
    return registry_manager.get_registry()

@router.get("/capabilities")
async def get_capabilities_text():
    """Get formatted capabilities text for LLM"""
    
    if not registry_manager:
        raise HTTPException(status_code=500, detail="Registry manager not initialized")
    
    return {"capabilities": registry_manager.get_all_capabilities_text()}
