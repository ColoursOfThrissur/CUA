"""
Services API - Manage pending service approvals
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/services", tags=["services"])

# Global instances (set by server.py)
_pending_services_manager = None
_service_injector = None

def set_services_dependencies(pending_manager, injector):
    global _pending_services_manager, _service_injector
    _pending_services_manager = pending_manager
    _service_injector = injector

class ApproveServiceRequest(BaseModel):
    reason: Optional[str] = None

class RejectServiceRequest(BaseModel):
    reason: str

@router.get("/pending")
async def get_pending_services():
    """Get all pending service approvals"""
    if not _pending_services_manager:
        raise HTTPException(status_code=503, detail="Services manager not initialized")
    
    pending = _pending_services_manager.get_pending_services()
    return {"success": True, "pending_services": pending}

@router.get("/{service_id}")
async def get_service_details(service_id: str):
    """Get details of a pending service"""
    if not _pending_services_manager:
        raise HTTPException(status_code=503, detail="Services manager not initialized")
    
    service = _pending_services_manager.get_service(service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    return {"success": True, "service": service}

@router.post("/{service_id}/approve")
async def approve_service(service_id: str, request: ApproveServiceRequest):
    """Approve and inject a pending service"""
    if not _pending_services_manager or not _service_injector:
        raise HTTPException(status_code=503, detail="Services not initialized")
    
    service = _pending_services_manager.get_service(service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    # Inject service
    result = _service_injector.inject_service(
        service["service_name"],
        service.get("method_name"),
        service["code"],
        service["type"]
    )
    
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("error", "Injection failed"))
    
    # Mark as approved
    _pending_services_manager.approve_service(service_id)
    
    return {
        "success": True,
        "message": f"Service {service['service_name']} approved and injected",
        "injection_result": result
    }

@router.post("/{service_id}/reject")
async def reject_service(service_id: str, request: RejectServiceRequest):
    """Reject a pending service"""
    if not _pending_services_manager:
        raise HTTPException(status_code=503, detail="Services manager not initialized")
    
    success = _pending_services_manager.reject_service(service_id, request.reason)
    if not success:
        raise HTTPException(status_code=404, detail="Service not found")
    
    return {"success": True, "message": "Service rejected"}
