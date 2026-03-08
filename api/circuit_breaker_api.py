"""Circuit Breaker API - Monitor and manage circuit breaker state."""
from fastapi import APIRouter, HTTPException
from typing import Dict, List
from core.circuit_breaker import get_circuit_breaker, CircuitState

router = APIRouter(prefix="/circuit-breaker", tags=["circuit-breaker"])


@router.get("/status")
def get_circuit_breaker_status() -> Dict:
    """Get overall circuit breaker status"""
    cb = get_circuit_breaker()
    
    all_circuits = {}
    for tool_name in cb.circuits.keys():
        all_circuits[tool_name] = cb.get_stats(tool_name)
    
    open_circuits = cb.get_all_open_circuits()
    
    return {
        "total_circuits": len(all_circuits),
        "open_circuits": len(open_circuits),
        "circuits": all_circuits,
        "quarantined_tools": open_circuits
    }


@router.get("/tool/{tool_name}")
def get_tool_circuit_status(tool_name: str) -> Dict:
    """Get circuit status for specific tool"""
    cb = get_circuit_breaker()
    return cb.get_stats(tool_name)


@router.post("/tool/{tool_name}/reset")
def reset_tool_circuit(tool_name: str) -> Dict:
    """Manually reset circuit for a tool"""
    cb = get_circuit_breaker()
    cb.reset(tool_name)
    return {"message": f"Circuit reset for {tool_name}", "status": cb.get_stats(tool_name)}


@router.get("/quarantined")
def get_quarantined_tools() -> Dict:
    """Get list of quarantined (open circuit) tools"""
    cb = get_circuit_breaker()
    open_circuits = cb.get_all_open_circuits()
    
    details = {}
    for tool_name in open_circuits:
        details[tool_name] = cb.get_stats(tool_name)
    
    return {
        "count": len(open_circuits),
        "tools": open_circuits,
        "details": details
    }


@router.post("/reset-all")
def reset_all_circuits() -> Dict:
    """Reset all circuits"""
    cb = get_circuit_breaker()
    reset_count = 0
    
    for tool_name in list(cb.circuits.keys()):
        cb.reset(tool_name)
        reset_count += 1
    
    return {"message": f"Reset {reset_count} circuits"}
