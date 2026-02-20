"""API for tool evolution."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict

router = APIRouter()

_evolution_orchestrator = None
_pending_manager = None


def set_evolution_dependencies(orchestrator, pending_manager):
    """Set dependencies."""
    global _evolution_orchestrator, _pending_manager
    _evolution_orchestrator = orchestrator
    _pending_manager = pending_manager


class EvolveToolRequest(BaseModel):
    tool_name: str
    user_prompt: Optional[str] = None


@router.post("/evolution/evolve")
async def evolve_tool(request: EvolveToolRequest):
    """Start tool evolution process."""
    if not _evolution_orchestrator:
        raise HTTPException(status_code=500, detail="Evolution system not initialized")
    
    success, message = _evolution_orchestrator.evolve_tool(
        request.tool_name,
        request.user_prompt
    )
    
    conversation_log = _evolution_orchestrator.get_conversation_log()
    
    return {
        "success": success,
        "message": message,
        "conversation_log": conversation_log
    }


@router.get("/evolution/pending")
async def get_pending_evolutions():
    """Get all pending evolutions."""
    if not _pending_manager:
        raise HTTPException(status_code=500, detail="Pending manager not initialized")
    
    pending = _pending_manager.get_all_pending()
    
    return {"pending_evolutions": pending}


@router.post("/evolution/approve/{tool_name}")
async def approve_evolution(tool_name: str):
    """Approve pending evolution."""
    if not _pending_manager:
        raise HTTPException(status_code=500, detail="Pending manager not initialized")
    
    evolution = _pending_manager.get_pending_evolution(tool_name)
    if not evolution:
        raise HTTPException(status_code=404, detail="Evolution not found")
    
    # Re-check dependencies before approval
    from core.dependency_checker import DependencyChecker
    checker = DependencyChecker()
    improved_code = evolution.get("improved_code", "")
    report = checker.check_code(improved_code)
    
    # Update dependencies in proposal
    if "proposal" not in evolution:
        evolution["proposal"] = {}
    evolution["proposal"]["dependencies"] = {
        "missing_libraries": report.missing_libraries,
        "missing_services": report.missing_services
    }
    _pending_manager._save(_pending_manager._load())
    
    # Check if dependencies still missing
    if report.has_missing():
        return {
            "success": False,
            "needs_dependencies": True,
            "dependencies": {
                "missing_libraries": report.missing_libraries,
                "missing_services": report.missing_services
            },
            "message": "Please resolve dependencies first"
        }
    
    success = _pending_manager.approve_evolution(tool_name)
    
    if not success:
        raise HTTPException(status_code=404, detail="Evolution not found")
    
    return {"success": True, "message": f"Evolution approved: {tool_name}"}


@router.post("/evolution/reject/{tool_name}")
async def reject_evolution(tool_name: str):
    """Reject pending evolution."""
    if not _pending_manager:
        raise HTTPException(status_code=500, detail="Pending manager not initialized")
    
    success = _pending_manager.reject_evolution(tool_name)
    
    if not success:
        raise HTTPException(status_code=404, detail="Evolution not found")
    
    return {"success": True, "message": f"Evolution rejected: {tool_name}"}


@router.get("/evolution/conversation/{tool_name}")
async def get_evolution_conversation(tool_name: str):
    """Get conversation log for evolution."""
    if not _pending_manager:
        raise HTTPException(status_code=500, detail="Pending manager not initialized")
    
    evolution = _pending_manager.get_pending_evolution(tool_name)
    
    if not evolution:
        raise HTTPException(status_code=404, detail="Evolution not found")
    
    return {
        "tool_name": tool_name,
        "conversation_log": evolution.get("conversation_log", []),
        "proposal": evolution.get("proposal", {}),
        "health_before": evolution.get("health_before", 0),
        "dependencies": evolution.get("proposal", {}).get("dependencies")
    }


@router.post("/evolution/resolve-dependencies/{tool_name}")
async def resolve_dependencies(tool_name: str, action: str, items: List[str]):
    """Resolve missing dependencies.
    
    action: 'install' for libraries, 'generate' for services, 'skip' to ignore
    items: list of library/service names to resolve
    """
    if not _pending_manager:
        raise HTTPException(status_code=500, detail="Pending manager not initialized")
    
    evolution = _pending_manager.get_pending_evolution(tool_name)
    if not evolution:
        raise HTTPException(status_code=404, detail="Evolution not found")
    
    from core.dependency_resolver import DependencyResolver
    resolver = DependencyResolver(llm_client=None)  # TODO: inject LLM client
    
    results = []
    
    if action == "install":
        for lib in items:
            success, msg = resolver.install_library(lib)
            results.append({"item": lib, "success": success, "message": msg})
    
    elif action == "generate":
        for service in items:
            success, code = resolver.generate_service(service)
            results.append({"item": service, "success": success, "code": code if success else None})
    
    elif action == "skip":
        # Remove dependencies from proposal
        if "dependencies" in evolution.get("proposal", {}):
            deps = evolution["proposal"]["dependencies"]
            deps["missing_libraries"] = [l for l in deps.get("missing_libraries", []) if l not in items]
            deps["missing_services"] = [s for s in deps.get("missing_services", []) if s not in items]
            _pending_manager._save(_pending_manager._load())
        results.append({"action": "skipped", "items": items})
    
    return {"success": True, "results": results}
