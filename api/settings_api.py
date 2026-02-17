"""
Settings API - Model selection and configuration
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/settings", tags=["settings"])

# Global LLM client reference (set by server)
llm_client = None

def set_llm_client(client):
    global llm_client
    llm_client = client

class ModelChangeRequest(BaseModel):
    model: str

@router.get("/models")
async def get_available_models():
    """Get list of available LLM models"""
    if not llm_client:
        raise HTTPException(status_code=503, detail="LLM client not initialized")
    
    models = llm_client.get_available_models()
    current = llm_client.model
    
    return {
        "current_model": current,
        "available_models": models
    }

@router.post("/model")
async def change_model(request: ModelChangeRequest):
    """Switch to different LLM model"""
    if not llm_client:
        raise HTTPException(status_code=503, detail="LLM client not initialized")
    
    success = llm_client.set_model(request.model)
    
    if success:
        return {
            "success": True,
            "model": llm_client.model,
            "message": f"Switched to model: {llm_client.model}"
        }
    else:
        raise HTTPException(status_code=400, detail="Failed to switch model")

@router.post("/reload-config")
async def reload_config():
    """Reload configuration from file"""
    try:
        from core.config_manager import reload_config
        reload_config()
        return {
            "success": True,
            "message": "Configuration reloaded successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reload config: {str(e)}")
