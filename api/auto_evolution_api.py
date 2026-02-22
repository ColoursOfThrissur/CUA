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
from core.auto_evolution_orchestrator import AutoEvolutionOrchestrator

router = APIRouter(prefix="/auto-evolution", tags=["auto-evolution"])

# Global orchestrator instance
orchestrator: Optional[AutoEvolutionOrchestrator] = None

class ConfigUpdate(BaseModel):
    mode: Optional[str] = None
    scan_interval: Optional[int] = None
    max_concurrent: Optional[int] = None
    min_health_threshold: Optional[int] = None
    auto_approve_threshold: Optional[int] = None
    learning_enabled: Optional[bool] = None

@router.post("/start")
async def start_orchestrator():
    """Start auto-evolution engine"""
    global orchestrator
    
    if orchestrator and orchestrator.running:
        raise HTTPException(400, "Orchestrator already running")
    
    # Get dependencies from server (will be set by server.py)
    try:
        from api.server import llm_client, registry
        orchestrator = AutoEvolutionOrchestrator(llm_client, registry)
        await orchestrator.start()
    except Exception as e:
        raise HTTPException(500, f"Failed to start: {str(e)}")
    
    return {"success": True, "message": "Auto-evolution started"}

@router.post("/stop")
async def stop_orchestrator():
    """Stop auto-evolution engine"""
    global orchestrator
    
    if not orchestrator or not orchestrator.running:
        raise HTTPException(400, "Orchestrator not running")
        
    await orchestrator.stop()
    
    return {"success": True, "message": "Auto-evolution stopped"}

@router.get("/status")
async def get_status():
    """Get orchestrator status"""
    global orchestrator
    
    if not orchestrator:
        return {"running": False, "message": "Orchestrator not initialized"}
        
    return orchestrator.get_status()

@router.post("/config")
async def update_config(config: ConfigUpdate):
    """Update orchestrator configuration"""
    global orchestrator
    
    if not orchestrator:
        raise HTTPException(400, "Orchestrator not initialized")
        
    config_dict = {k: v for k, v in config.dict().items() if v is not None}
    orchestrator.update_config(config_dict)
    
    return {"success": True, "config": orchestrator.config}

@router.get("/queue")
async def get_queue():
    """Get current evolution queue"""
    global orchestrator
    
    if not orchestrator:
        raise HTTPException(400, "Orchestrator not initialized")
    
    # Manually add priority_score to each queue item
    queue_with_priority = []
    for e in orchestrator.queue.queue:
        item = asdict(e)
        item['priority_score'] = e.priority_score  # Add computed property
        queue_with_priority.append(item)
        
    return {
        "queue": queue_with_priority,
        "in_progress": orchestrator.queue.in_progress
    }

@router.post("/trigger-scan")
async def trigger_scan():
    """Manually trigger tool health scan"""
    global orchestrator
    
    try:
        if not orchestrator:
            orchestrator = AutoEvolutionOrchestrator()
        
        # Clear queue before scanning
        orchestrator.queue.clear_queue()
        
        await orchestrator._scan_and_queue()
        return {"success": True, "message": "Scan completed", "queue_size": len(orchestrator.queue.queue)}
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        raise HTTPException(500, f"Scan failed: {str(e)}\n{error_detail}")
