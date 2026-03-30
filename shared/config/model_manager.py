"""
Model Manager - Orchestrates multiple models for different tasks.

Strategy:
- qwen3.5:9b + mistral:7b → Always loaded (chat + planning)
- qwen2.5-coder:14b → Loaded on-demand for tool creation/evolution
"""
import logging
import requests
from typing import Optional, Literal

logger = logging.getLogger(__name__)

ModelRole = Literal["chat", "planning", "code", "autonomy"]

class ModelManager:
    """Manages multiple models and handles loading/unloading."""
    
    def __init__(self, llm_client, ollama_url: str = "http://localhost:11434"):
        self.llm_client = llm_client
        self.ollama_url = ollama_url
        
        # Model assignments from config
        from shared.config.config_manager import get_config
        config = get_config()
        
        # Load raw YAML to get models dict
        import yaml
        from pathlib import Path
        models_dict = {}
        try:
            config_file = Path("config.yaml")
            if config_file.exists():
                with open(config_file, 'r') as f:
                    raw_config = yaml.safe_load(f) or {}
                    models_dict = raw_config.get('llm', {}).get('models', {})
        except Exception:
            pass
        
        # Read from top-level config fields and resolve aliases
        self.chat_model = self._resolve_model_name(getattr(config.llm, 'chat_model', 'qwen3.5:9b'), models_dict)
        self.planning_model = self._resolve_model_name(getattr(config.llm, 'planning_model', 'mistral:7b'), models_dict)
        self.code_model = self._resolve_model_name(getattr(config.llm, 'code_model', 'qwen2.5-coder:14b'), models_dict)
        self.autonomy_model = self._resolve_model_name(getattr(config.llm, 'autonomy_model', self.chat_model), models_dict)
        
        # Track current state and sync LLM client
        self.current_model = self.chat_model
        self.code_model_loaded = False
        
        # CRITICAL: Sync LLM client to the resolved chat model
        # Without this, LLM client stays on its default (qwen2.5-coder:14b)
        self.llm_client.set_model(self.chat_model)
        
        logger.info(f"Model Manager initialized:")
        logger.info(f"  Chat: {self.chat_model}")
        logger.info(f"  Planning: {self.planning_model}")
        logger.info(f"  Code: {self.code_model}")
        logger.info(f"  Autonomy: {self.autonomy_model}")
        logger.info(f"  LLM client synced to: {self.llm_client.model}")
    
    def _resolve_model_name(self, model_key: str, models_dict: dict) -> str:
        """Resolve model alias to actual model name from config.llm.models."""
        logger.debug(f"Resolving model_key='{model_key}', models_dict keys={list(models_dict.keys())}")
        if model_key in models_dict:
            model_config = models_dict[model_key]
            logger.debug(f"Found config for '{model_key}': {model_config}")
            if isinstance(model_config, dict) and 'name' in model_config:
                resolved = model_config['name']
                logger.info(f"Resolved '{model_key}' -> '{resolved}'")
                return resolved
        # Fallback: return as-is if not found in models dict
        logger.warning(f"Could not resolve '{model_key}', using as-is")
        return model_key
    
    def get_model_for_role(self, role: ModelRole) -> str:
        """Get the model name for a specific role."""
        if role == "chat":
            return self.chat_model
        elif role == "planning":
            return self.planning_model
        elif role == "code":
            return self.code_model
        elif role == "autonomy":
            return self.autonomy_model
        return self.chat_model
    
    def switch_to(self, role: ModelRole) -> bool:
        """Switch to the model for the given role."""
        target_model = self.get_model_for_role(role)
        
        logger.debug(f"[MODEL_MANAGER] switch_to('{role}') called")
        logger.debug(f"[MODEL_MANAGER]   current_model: {self.current_model}")
        logger.debug(f"[MODEL_MANAGER]   target_model: {target_model}")
        logger.debug(f"[MODEL_MANAGER]   llm_client.model: {self.llm_client.model}")
        
        if self.current_model == target_model:
            logger.debug(f"[MODEL_MANAGER] Already using {target_model}, checking sync...")
            if self.llm_client.model != target_model:
                logger.warning(f"[MODEL_MANAGER] DESYNC DETECTED! llm_client.model={self.llm_client.model} but current_model={self.current_model}")
                logger.debug(f"[MODEL_MANAGER] Forcing sync: set_model({target_model})")
                self.llm_client.set_model(target_model)
            return True
        
        logger.debug(f"[MODEL_MANAGER] Switching from {self.current_model} to {target_model} (role={role})")
        self.llm_client.set_model(target_model)
        self.current_model = target_model
        logger.debug(f"[MODEL_MANAGER] After switch: llm_client.model={self.llm_client.model}")
        
        # Warm up the new model to ensure it's loaded
        try:
            self.llm_client.warmup_model()
        except Exception as e:
            logger.warning(f"Failed to warm up model {target_model}: {e}")
        
        return True
    
    def load_code_model(self) -> bool:
        """Load code model (qwen2.5-coder:14b) for tool creation/evolution."""
        if self.code_model_loaded:
            logger.debug(f"Code model {self.code_model} already loaded")
            return True
        
        logger.info(f"Loading code model: {self.code_model}")
        
        # Unload chat models to free VRAM
        self._unload_model(self.chat_model)
        self._unload_model(self.planning_model)
        
        # Switch to code model
        self.llm_client.set_model(self.code_model)
        self.current_model = self.code_model
        
        # Warm up code model
        try:
            self.llm_client.warmup_model()
            self.code_model_loaded = True
            logger.info(f"Code model {self.code_model} loaded successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to load code model: {e}")
            return False
    
    def unload_code_model(self) -> bool:
        """Unload code model and restore chat models."""
        if not self.code_model_loaded:
            logger.debug("Code model not loaded, nothing to unload")
            return True
        
        logger.info(f"Unloading code model: {self.code_model}")
        
        # Unload code model
        self._unload_model(self.code_model)
        self.code_model_loaded = False
        
        # Restore chat model
        self.llm_client.set_model(self.chat_model)
        self.current_model = self.chat_model
        
        # Warm up chat models
        try:
            self.llm_client.warmup_model()
            logger.info(f"Restored to chat model: {self.chat_model}")
            return True
        except Exception as e:
            logger.error(f"Failed to restore chat model: {e}")
            return False
    
    def _unload_model(self, model_name: str):
        """Unload a specific model from Ollama."""
        try:
            logger.debug(f"Unloading model: {model_name}")
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={"model": model_name, "prompt": "", "keep_alive": 0},
                timeout=5
            )
            if response.status_code == 200:
                logger.debug(f"Model {model_name} unloaded")
            else:
                logger.warning(f"Model unload returned HTTP {response.status_code}")
        except Exception as e:
            logger.warning(f"Failed to unload model {model_name}: {e}")
    
    def ensure_chat_models_loaded(self):
        """Ensure chat and planning models are loaded (unload code model if needed)."""
        if self.code_model_loaded:
            logger.info("Code model is loaded, switching back to chat models")
            self.unload_code_model()


# Global instance
_model_manager_instance: Optional[ModelManager] = None

def get_model_manager(llm_client=None) -> ModelManager:
    """Get or create global model manager instance."""
    global _model_manager_instance
    if _model_manager_instance is None:
        if llm_client is None:
            from planner.llm_client import get_llm_client
            llm_client = get_llm_client()
        _model_manager_instance = ModelManager(llm_client)
    return _model_manager_instance
