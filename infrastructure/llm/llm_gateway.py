"""LLM Gateway - Abstract interface for LLM interactions."""
from abc import ABC, abstractmethod
from typing import Optional


class LLMGateway(ABC):
    """Interface for LLM interactions."""
    
    @abstractmethod
    def generate_plan(self, prompt: str, temperature: float = 0.3, max_tokens: Optional[int] = None) -> str:
        """Generate plan from prompt."""
        pass
    
    @abstractmethod
    def analyze_completion(self, prompt: str, temperature: float = 0.1, max_tokens: int = 150) -> str:
        """Analyze task completion."""
        pass
    
    @abstractmethod
    def check_enrichment(self, prompt: str, temperature: float = 0.1, max_tokens: int = 300) -> str:
        """Check if enrichment needed."""
        pass


class OllamaLLMGateway(LLMGateway):
    """Ollama implementation of LLM gateway."""
    
    def __init__(self, llm_client):
        self._client = llm_client
    
    def generate_plan(self, prompt: str, temperature: float = 0.3, max_tokens: Optional[int] = None) -> str:
        """Generate plan using planning model."""
        from shared.config.model_manager import get_model_manager
        model_manager = get_model_manager(self._client)
        model_manager.switch_to("planning")
        try:
            return self._client._call_llm(prompt, temperature, max_tokens, expect_json=True)
        finally:
            model_manager.switch_to("chat")
    
    def analyze_completion(self, prompt: str, temperature: float = 0.1, max_tokens: int = 150) -> str:
        """Analyze completion using planning model."""
        from shared.config.model_manager import get_model_manager
        model_manager = get_model_manager(self._client)
        model_manager.switch_to("planning")
        try:
            return self._client._call_llm(prompt, temperature, max_tokens, expect_json=True)
        finally:
            model_manager.switch_to("chat")
    
    def check_enrichment(self, prompt: str, temperature: float = 0.1, max_tokens: int = 300) -> str:
        """Check enrichment using planning model."""
        from shared.config.model_manager import get_model_manager
        model_manager = get_model_manager(self._client)
        model_manager.switch_to("planning")
        try:
            return self._client._call_llm(prompt, temperature, max_tokens, expect_json=True)
        finally:
            model_manager.switch_to("chat")
