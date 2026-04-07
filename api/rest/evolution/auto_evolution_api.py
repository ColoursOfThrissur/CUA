"""
Auto-Evolution API - Control and monitor automatic tool improvements
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Optional
from dataclasses import asdict
from application.use_cases.autonomy.auto_evolution_orchestrator import AutoEvolutionOrchestrator
from application.use_cases.autonomy.auto_evolution_trigger import AutoEvolutionTrigger

router = APIRouter(prefix="/auto-evolution", tags=["auto-evolution"])

# Global instances
orchestrator: Optional[AutoEvolutionOrchestrator] = None
trigger_manager: Optional[AutoEvolutionTrigger] = None
coordinated_engine = None


def set_coordinated_engine(engine):
    global coordinated_engine
    coordinated_engine = engine


def _reload_mode_enabled() -> bool:
    return str(os.getenv("CUA_RELOAD_MODE", "0")).strip().lower() in {"1", "true", "yes", "on"}


def _coordinated_reload_block_reason() -> str:
    return (
        "Coordinated autonomy is disabled while the backend is running in reload mode. "
        "Run the server without reload for unattended create/evolve cycles."
    )


def _get_active_orchestrator():
    return coordinated_engine.auto_orchestrator if coordinated_engine else orchestrator


def _require_active_orchestrator():
    active_orch = _get_active_orchestrator()
    if not active_orch:
        raise HTTPException(400, "Orchestrator not initialized")
    return active_orch

class ConfigUpdate(BaseModel):
    mode: Optional[str] = None
    scan_interval: Optional[int] = None
    max_concurrent: Optional[int] = None
    min_health_threshold: Optional[int] = None
    auto_approve_threshold: Optional[int] = None
    learning_enabled: Optional[bool] = None


class CoordinatorConfigUpdate(BaseModel):
    interval_seconds: Optional[int] = None
    improvement_iterations_per_cycle: Optional[int] = None
    max_evolutions_per_cycle: Optional[int] = None
    dry_run: Optional[bool] = None
    min_usefulness_score: Optional[float] = None
    max_consecutive_low_value_cycles: Optional[int] = None
    pause_on_low_value: Optional[bool] = None

@router.post("/start")
async def start_orchestrator():
    """Start auto-evolution engine"""
    global orchestrator, trigger_manager
    
    if orchestrator and orchestrator.running:
        raise HTTPException(400, "Orchestrator already running")
    
    try:
        from api.server import llm_client, registry
        orchestrator = AutoEvolutionOrchestrator(llm_client, registry)
        await orchestrator.start()
        
        # Start trigger manager
        trigger_manager = AutoEvolutionTrigger(orchestrator)
        await trigger_manager.start()
    except Exception as e:
        raise HTTPException(500, f"Failed to start: {str(e)}")
    
    return {"success": True, "message": "Auto-evolution started"}

@router.post("/stop")
async def stop_orchestrator():
    """Stop auto-evolution engine"""
    global orchestrator, trigger_manager
    
    if not orchestrator or not orchestrator.running:
        raise HTTPException(400, "Orchestrator not running")
    
    if trigger_manager:
        await trigger_manager.stop()
        
    await orchestrator.stop()
    
    return {"success": True, "message": "Auto-evolution stopped"}

@router.get("/status")
async def get_status():
    """Get orchestrator status"""
    global trigger_manager
    active_orch = _get_active_orchestrator()
    if not active_orch:
        return {"running": False, "message": "Orchestrator not initialized"}
    status = active_orch.get_status()
    if trigger_manager:
        status["triggers"] = trigger_manager.get_status()
    return status

@router.post("/config")
async def update_config(config: ConfigUpdate):
    """Update orchestrator configuration"""
    active_orch = _require_active_orchestrator()
    config_dict = {k: v for k, v in config.model_dump().items() if v is not None}
    active_orch.update_config(config_dict)
    
    return {"success": True, "config": active_orch.config}

@router.get("/queue")
async def get_queue():
    """Get current evolution queue"""
    active_orch = _get_active_orchestrator()
    if not active_orch:
        return {"queue": [], "in_progress": [], "running": False, "message": "Orchestrator not initialized"}
    queue_with_priority = []
    for e in active_orch.queue.queue:
        item = asdict(e)
        item['priority_score'] = e.priority_score
        queue_with_priority.append(item)
    return {"queue": queue_with_priority, "in_progress": active_orch.queue.in_progress}

@router.post("/trigger-scan")
async def trigger_scan():
    """Manually trigger tool health scan"""
    global orchestrator
    try:
        active_orch = _get_active_orchestrator()
        if not active_orch:
            from api.server import llm_client, registry
            orchestrator = AutoEvolutionOrchestrator(llm_client, registry)
            active_orch = orchestrator
        await active_orch.ensure_initialized()
        active_orch.queue.clear_queue()
        await active_orch._scan_and_queue()
        return {"success": True, "message": "Scan completed", "queue_size": len(active_orch.queue.queue)}
    except Exception as e:
        import traceback
        raise HTTPException(500, f"Scan failed: {str(e)}\n{traceback.format_exc()}")


@router.post("/triggers/enable")
async def enable_trigger(trigger_type: str, config: Dict = None):
    """Enable a trigger"""
    global trigger_manager
    
    if not trigger_manager:
        raise HTTPException(400, "Trigger manager not initialized")
    
    trigger_manager.enable_trigger(trigger_type, **(config or {}))
    return {"success": True, "trigger": trigger_type, "config": config}


@router.post("/triggers/disable")
async def disable_trigger(trigger_type: str):
    """Disable a trigger"""
    global trigger_manager
    
    if not trigger_manager:
        raise HTTPException(400, "Trigger manager not initialized")
    
    trigger_manager.disable_trigger(trigger_type)
    return {"success": True, "trigger": trigger_type}


@router.get("/triggers/status")
async def get_triggers_status():
    """Get trigger status"""
    global trigger_manager
    
    if not trigger_manager:
        return {"running": False, "triggers": {}}
    
    return trigger_manager.get_status()


@router.post("/coordinated/start")
async def start_coordinated_engine():
    if _reload_mode_enabled():
        raise HTTPException(409, _coordinated_reload_block_reason())
    if not coordinated_engine:
        raise HTTPException(400, "Coordinated engine not initialized")
    return await coordinated_engine.start()


@router.post("/coordinated/stop")
async def stop_coordinated_engine():
    if not coordinated_engine:
        raise HTTPException(400, "Coordinated engine not initialized")
    return await coordinated_engine.stop()


@router.post("/coordinated/run-cycle")
async def run_coordinated_cycle():
    if _reload_mode_enabled():
        raise HTTPException(409, _coordinated_reload_block_reason())
    if not coordinated_engine:
        raise HTTPException(400, "Coordinated engine not initialized")
    return await coordinated_engine.run_cycle()


@router.get("/coordinated/status")
async def get_coordinated_status():
    if not coordinated_engine:
        return {
            "running": False,
            "message": "Coordinated engine not initialized",
            "reload_mode": _reload_mode_enabled(),
            "reload_blocked": _reload_mode_enabled(),
        }
    status = coordinated_engine.get_status()
    status["reload_mode"] = _reload_mode_enabled()
    status["reload_blocked"] = _reload_mode_enabled()
    if _reload_mode_enabled():
        status["reload_warning"] = _coordinated_reload_block_reason()
    return status


@router.post("/coordinated/config")
async def update_coordinated_config(config: CoordinatorConfigUpdate):
    if not coordinated_engine:
        raise HTTPException(400, "Coordinated engine not initialized")
    config_dict = {k: v for k, v in config.model_dump().items() if v is not None}
    return {"success": True, "config": coordinated_engine.update_config(config_dict)}
