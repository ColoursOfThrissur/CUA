"""
Settings API - Model selection and configuration
"""
import yaml
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/settings", tags=["settings"])

CONFIG_PATH = Path("config.yaml")

# Global LLM client reference (set by server)
llm_client = None

def set_llm_client(client):
    global llm_client
    llm_client = client

class ModelChangeRequest(BaseModel):
    model: str

class ProviderUpdateRequest(BaseModel):
    provider: str          # "ollama" | "openai" | "gemini"
    model: str             # model key from config or raw model name
    api_key: Optional[str] = ""
    base_url: Optional[str] = ""

class AddModelRequest(BaseModel):
    key: str               # config key e.g. "my-gpt4"
    name: str              # actual model name e.g. "gpt-4o"
    description: Optional[str] = ""
    context_length: Optional[int] = 4096


def _load_yaml() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r") as f:
            return yaml.safe_load(f) or {}
    return {}

def _save_yaml(data: dict):
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


@router.get("/models")
async def get_available_models():
    """Get list of available LLM models"""
    if not llm_client:
        raise HTTPException(status_code=503, detail="LLM client not initialized")
    models = llm_client.get_available_models()
    current = llm_client.model
    return {"current_model": current, "available_models": models}


@router.get("/config")
async def get_llm_config():
    """Return current LLM provider config (api_key masked)."""
    if not llm_client:
        raise HTTPException(status_code=503, detail="LLM client not initialized")
    data = _load_yaml()
    llm_cfg = data.get("llm", {})
    raw_key = llm_cfg.get("api_key", "")
    masked = ("*" * (len(raw_key) - 4) + raw_key[-4:]) if len(raw_key) > 4 else ("*" * len(raw_key))
    return {
        "provider": llm_cfg.get("provider", "ollama"),
        "model": llm_client.model,
        "api_key_set": bool(raw_key),
        "api_key_masked": masked if raw_key else "",
        "base_url": llm_cfg.get("base_url", ""),
        "ollama_url": llm_cfg.get("ollama_url", "http://localhost:11434"),
        "available_models": llm_client.get_available_models(),
    }


@router.post("/provider")
async def update_provider(request: ProviderUpdateRequest):
    """Switch provider + model + credentials and persist to config.yaml."""
    if not llm_client:
        raise HTTPException(status_code=503, detail="LLM client not initialized")

    provider = request.provider.lower()
    if provider not in ("ollama", "openai", "gemini"):
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    # Persist to config.yaml
    data = _load_yaml()
    llm_section = data.setdefault("llm", {})
    llm_section["provider"] = provider
    llm_section["default_model"] = request.model
    if request.api_key:
        llm_section["api_key"] = request.api_key
    if request.base_url is not None:
        llm_section["base_url"] = request.base_url
    _save_yaml(data)

    # Apply to live client
    from shared.config.config_manager import reload_config
    reload_config()

    from shared.config.config_manager import get_config
    cfg = get_config()

    llm_client.provider = provider
    # Refresh available_models from the newly saved config before resolving model name
    llm_client.available_models = data["llm"].get("models", {})
    llm_client.set_model(request.model)

    # Rebuild api provider on the live client
    llm_client._api_provider = llm_client._build_api_provider(cfg)

    # Also update ToolCallingClient if accessible
    try:
        from api.server import tool_calling_client
        if tool_calling_client:
            tool_calling_client.provider = provider
            tool_calling_client.model = llm_client.model
            tool_calling_client._api_key = cfg.llm.api_key
            tool_calling_client._base_url = cfg.llm.base_url
    except Exception:
        pass

    return {
        "success": True,
        "provider": provider,
        "model": llm_client.model,
        "message": f"Switched to {provider} / {llm_client.model}",
    }


@router.post("/add-model")
async def add_model(request: AddModelRequest):
    """Add a custom model entry to config.yaml."""
    data = _load_yaml()
    models = data.setdefault("llm", {}).setdefault("models", {})
    models[request.key] = {
        "name": request.name,
        "context_length": request.context_length,
        "description": request.description or request.name,
        "strengths": [],
    }
    _save_yaml(data)
    if llm_client:
        llm_client.available_models = data["llm"]["models"]
    return {"success": True, "key": request.key, "name": request.name}


@router.post("/model")
async def change_model(request: ModelChangeRequest):
    """Switch to different LLM model (runtime only, no config write)."""
    if not llm_client:
        raise HTTPException(status_code=503, detail="LLM client not initialized")
    success = llm_client.set_model(request.model)
    if success:
        return {"success": True, "model": llm_client.model, "message": f"Switched to model: {llm_client.model}"}
    raise HTTPException(status_code=400, detail="Failed to switch model")


@router.post("/reload-config")
async def reload_config_endpoint():
    """Reload configuration from file"""
    try:
        from shared.config.config_manager import reload_config
        reload_config()
        return {"success": True, "message": "Configuration reloaded successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reload config: {str(e)}")
