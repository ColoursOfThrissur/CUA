"""
Tools API - Sync tool capabilities
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, List, Tuple

router = APIRouter(prefix="/api/tools", tags=["tools"])

# Global instances
registry_manager = None
llm_client_instance = None
runtime_registry = None
tool_registrar = None
tool_orchestrator = None

def set_registry_manager(manager):
    global registry_manager
    registry_manager = manager

def set_llm_client_for_sync(client):
    global llm_client_instance
    llm_client_instance = client

def set_runtime_registry(registry):
    global runtime_registry
    runtime_registry = registry

def set_tool_registrar_for_sync(registrar):
    global tool_registrar
    tool_registrar = registrar

def set_tool_orchestrator_for_sync(orchestrator):
    global tool_orchestrator
    tool_orchestrator = orchestrator

class SyncResponse(BaseModel):
    success: bool
    synced: list
    failed: list
    timestamp: str
    message: str

def _discover_tool_files() -> Tuple[List[str], set]:
    """Return active tool files and pending file set."""
    from pathlib import Path
    import json

    tools_dir = Path("tools")
    primary_tools = []
    for tool_file in tools_dir.glob("*.py"):
        name = tool_file.name
        if name.startswith("_"):
            continue
        if name in {"web_content_extractor.py", "test_tool.py"} or name.endswith("_tool.py"):
            primary_tools.append(tool_file)

    experimental_tools = list((tools_dir / "experimental").glob("*.py"))
    tool_files = primary_tools + experimental_tools

    pending_files = set()
    try:
        pending_path = Path("data/pending_tools.json")
        if pending_path.exists():
            pending_data = json.loads(pending_path.read_text(encoding="utf-8"))
            for item in pending_data.get("pending", {}).values():
                p = item.get("tool_file")
                if p:
                    pending_files.add(str(Path(p)).replace("\\", "/"))
    except Exception:
        pass

    active = []
    for tool_file in tool_files:
        if tool_file.name.startswith("_") or tool_file.name.startswith("test_"):
            continue
        norm_path = str(tool_file).replace("\\", "/")
        if norm_path in pending_files:
            continue
        active.append(norm_path)
    return active, pending_files

def refresh_runtime_registry_from_files() -> Dict[str, List[Dict[str, str]]]:
    """Hot-refresh runtime registry using discovered active tool files."""
    refreshed: List[str] = []
    failed: List[Dict[str, str]] = []
    removed: List[str] = []
    if not runtime_registry or not tool_registrar:
        return {"refreshed": refreshed, "failed": failed, "removed": removed}
    
    # Always inject orchestrator to ensure it's available
    if tool_orchestrator:
        tool_registrar.orchestrator = tool_orchestrator

    active_files, _ = _discover_tool_files()
    active_class_names = set()
    try:
        from tools.capability_extractor import CapabilityExtractor
        extractor = CapabilityExtractor()
        for path in active_files:
            try:
                info = extractor.extract_from_file(path)
                if info and info.get("name"):
                    active_class_names.add(info["name"])
            except Exception:
                continue
    except Exception:
        active_class_names = set()

    # Remove stale runtime registrations that are no longer active sources.
    try:
        for _, tool_instance in list(tool_registrar.registered_tools.items()):
            class_name = tool_instance.__class__.__name__
            if active_class_names and class_name not in active_class_names:
                result = tool_registrar.unregister_tool(getattr(tool_instance, "name", class_name))
                if result.get("success"):
                    removed.append(class_name)
    except Exception:
        pass

    for path in active_files:
        result = tool_registrar.register_new_tool(path)
        if result.get("success"):
            refreshed.append(result.get("tool_name", path))
        else:
            print(f"[SYNC] Failed to load {path}: {result.get('error')}")
            failed.append({"file": path, "reason": str(result.get("error", "unknown"))})
    return {"refreshed": refreshed, "failed": failed, "removed": removed}

@router.post("/sync", response_model=SyncResponse)
async def sync_tool_capabilities():
    """Sync all tool capabilities using deterministic AST extraction"""
    
    if not registry_manager:
        raise HTTPException(status_code=500, detail="Registry manager not initialized")
    
    try:
        from tools.capability_extractor import CapabilityExtractor
        from datetime import datetime
        
        extractor = CapabilityExtractor()
        synced = []
        failed = []
        discovered_sources, _ = _discover_tool_files()

        for norm_path in discovered_sources:
            
            try:
                capabilities = extractor.extract_from_file(norm_path)
                if capabilities:
                    capabilities["source_file"] = norm_path
                    registry_manager.update_tool(capabilities)
                    synced.append(norm_path)
                else:
                    failed.append({"file": norm_path, "reason": "No capabilities found"})
            except Exception as e:
                failed.append({"file": norm_path, "reason": str(e)})

        # Remove stale/deleted tool entries from registry snapshot.
        removed_stale = 0
        try:
            removed_stale = registry_manager.prune_tools_not_in_sources(discovered_sources)
        except Exception:
            removed_stale = 0

        runtime_refresh = refresh_runtime_registry_from_files()
        
        message = f"Synced {len(synced)} tools using AST extraction"
        if failed:
            message += f", {len(failed)} failed"
        if removed_stale:
            message += f", removed {removed_stale} stale"
        if runtime_refresh["refreshed"] or runtime_refresh["failed"]:
            message += (
                f", runtime refreshed {len(runtime_refresh['refreshed'])}"
                f", runtime failed {len(runtime_refresh['failed'])}"
            )
        if runtime_refresh.get("removed"):
            message += f", runtime removed {len(runtime_refresh['removed'])}"
        
        return SyncResponse(
            success=len(synced) > 0,
            synced=synced,
            failed=failed,
            timestamp=datetime.now().isoformat(),
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
