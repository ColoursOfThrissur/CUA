"""
Pending Tools API Endpoints
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import inspect
import asyncio

router = APIRouter(prefix="/pending-tools", tags=["pending-tools"])

# Global instances (set from server)
pending_tools_manager = None
tool_registrar = None
registry_manager = None
approve_lock = asyncio.Lock()

def set_pending_tools_manager(ptm):
    global pending_tools_manager
    pending_tools_manager = ptm

def set_tool_registrar(tr):
    global tool_registrar
    tool_registrar = tr

def set_registry_manager_for_pending(manager):
    global registry_manager
    registry_manager = manager

class RejectRequest(BaseModel):
    reason: Optional[str] = ""


def _post_register_contract_check(tool_name: str):
    """Run non-invasive runtime contract checks after registration."""
    tool_instance = getattr(tool_registrar, "registered_tools", {}).get(tool_name)
    if not tool_instance:
        return False, "Registered tool instance not found"

    try:
        sig = inspect.signature(tool_instance.execute)
        params = list(sig.parameters.values())
    except Exception as e:
        return False, f"Unable to inspect execute() signature: {e}"

    # Bound methods expose either:
    # - execute(operation, parameters)
    # - execute(operation, **kwargs)
    if not params:
        return False, "execute() must accept at least operation"
    has_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params)
    supports_param_dict = len(params) >= 2
    if not has_kwargs and not supports_param_dict:
        return False, "execute() must support parameters dict or **kwargs"

    try:
        capabilities = tool_instance.get_capabilities()
    except Exception as e:
        return False, f"get_capabilities() failed: {e}"
    if not capabilities:
        return False, "No capabilities registered"

    for cap_name in capabilities.keys():
        capability = capabilities.get(cap_name)
        for param in getattr(capability, "parameters", []) or []:
            if getattr(param, "required", True) and getattr(param, "default", None) is not None:
                return False, (
                    f"Capability '{cap_name}' has parameter '{param.name}' with "
                    "required=True and a default value"
                )
        handler_name = f"_handle_{cap_name}"
        handler = getattr(tool_instance, handler_name, None)
        if not callable(handler):
            return False, f"Missing capability handler: {handler_name}"
    return True, ""

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

    async with approve_lock:
        # Get tool metadata
        tool = pending_tools_manager.get_tool(tool_id)
        if not tool:
            raise HTTPException(status_code=404, detail="Tool not found")
        
        # Register tool dynamically
        tool_file = tool.get('tool_file')
        if not tool_file:
            raise HTTPException(status_code=400, detail="No tool file specified")

        valid, contract_error = pending_tools_manager.validate_tool_file_contract(tool_file)
        if not valid:
            raise HTTPException(status_code=400, detail=f"Tool contract validation failed: {contract_error}")

        try:
            from tools.capability_extractor import CapabilityExtractor
            extracted = CapabilityExtractor().extract_from_file(tool_file)
            if not extracted or not extracted.get("operations"):
                raise HTTPException(status_code=400, detail="Tool has no extractable capabilities")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Capability extraction failed: {str(e)}")
        
        reg_result = tool_registrar.register_new_tool(tool_file)
        
        if not reg_result['success']:
            raise HTTPException(status_code=400, detail=f"Registration failed: {reg_result['error']}")

        smoke_ok, smoke_error = _post_register_contract_check(reg_result['tool_name'])
        if not smoke_ok:
            try:
                tool_registrar.unregister_tool(reg_result['tool_name'])
            except Exception:
                pass
            raise HTTPException(status_code=400, detail=f"Post-registration validation failed: {smoke_error}")
        
        # Mark as approved
        pending_tools_manager.approve_tool(tool_id)

        # Keep tool registry view in sync when possible.
        try:
            if registry_manager and extracted:
                extracted["source_file"] = str(tool_file).replace("\\", "/")
                registry_manager.update_tool(extracted)
        except Exception:
            # Registry sync should not block activation after successful runtime registration.
            pass
        
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
