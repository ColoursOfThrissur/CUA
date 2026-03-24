"""LLM service wrapper for tools"""

class LLMService:
    """Provides LLM capabilities to tools"""
    
    def __init__(self, llm_client):
        self._client = llm_client
    
    def generate(self, prompt: str, temperature: float = 0.7, max_tokens: int = 1000) -> str:
        """Generate text from prompt"""
        return self._client._call_llm(prompt, temperature=temperature, max_tokens=max_tokens, expect_json=False) or ""

    def generate_json(self, prompt: str, temperature: float = 0.3, max_tokens: int = 1000) -> dict:
        """Generate JSON response"""
        response = self._client._call_llm(prompt, temperature=temperature, max_tokens=max_tokens, expect_json=True)
        if response:
            return self._client._extract_json(response) or {}
        return {}
