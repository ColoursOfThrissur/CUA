import json
import requests
from typing import Dict, List, Optional
from dataclasses import dataclass

@dataclass
class LLMResponse:
    content: str
    confidence: float
    tokens_used: int
    response_time: float

class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "mistral:7b"):
        self.base_url = base_url
        self.model = model
        self.timeout = 30
    
    def generate_plan(self, user_intent: str, available_capabilities: List[Dict], 
                     context: Optional[str] = None) -> LLMResponse:
        """Generate execution plan with tool capability awareness"""
        
        # Build capability descriptions for LLM
        capability_text = self._format_capabilities(available_capabilities)
        
        prompt = f"""You are an autonomous agent that creates execution plans using available tools.

AVAILABLE CAPABILITIES:
{capability_text}

USER REQUEST: {user_intent}

{f"CONTEXT: {context}" if context else ""}

Create a JSON execution plan with these steps:
1. Analyze the request
2. Select appropriate tools and operations
3. Define parameters for each tool call

Response format:
{{
    "analysis": "brief analysis of the request",
    "steps": [
        {{
            "tool": "tool_name",
            "operation": "operation_name", 
            "parameters": {{"key": "value"}},
            "reasoning": "why this step is needed"
        }}
    ],
    "confidence": 0.85
}}

Plan:"""

        try:
            import time
            start_time = time.time()
            
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3, "num_predict": 1024}
                },
                timeout=self.timeout
            )
            
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                result = response.json()
                content = result.get("response", "")
                
                # Extract confidence from response if available
                confidence = self._extract_confidence(content)
                
                return LLMResponse(
                    content=content,
                    confidence=confidence,
                    tokens_used=result.get("eval_count", 0),
                    response_time=response_time
                )
            else:
                raise Exception(f"Ollama error: {response.status_code}")
                
        except Exception as e:
            return LLMResponse(
                content=f"Error: {str(e)}",
                confidence=0.0,
                tokens_used=0,
                response_time=0.0
            )
    
    def _format_capabilities(self, capabilities: List[Dict]) -> str:
        """Format capabilities for LLM consumption"""
        formatted = []
        for cap in capabilities:
            params = ", ".join([f"{p['name']}({p['type']})" for p in cap.get('parameters', [])])
            formatted.append(f"- {cap['name']}: {cap['description']} | Parameters: {params}")
        return "\n".join(formatted)
    
    def _extract_confidence(self, content: str) -> float:
        """Extract confidence score from LLM response"""
        try:
            # Try to parse JSON and extract confidence
            if "confidence" in content:
                import re
                match = re.search(r'"confidence":\s*([0-9.]+)', content)
                if match:
                    return float(match.group(1))
        except:
            pass
        return 0.7  # Default confidence