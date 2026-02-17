"""
LLM Client with strict schema enforcement
Supports Mistral 7B via Ollama
"""

import json
import requests
import yaml
from pathlib import Path
from typing import Optional, Dict, Any, List
from core.plan_schema import (
    ExecutionPlanSchema, 
    validate_plan_json, 
    LLM_PROMPT_TEMPLATE,
    PLAN_JSON_SCHEMA,
    FEW_SHOT_EXAMPLES
)

class LLMClient:
    """LLM client with strict schema validation"""
    
    def __init__(self, max_retries: int = None, model: str = None, ollama_url: str = None, config_path: str = "config.yaml", registry=None):
        from core.config_manager import get_config
        config = get_config()
        
        self.max_retries = max_retries or config.llm.max_retries
        self.schema = PLAN_JSON_SCHEMA
        self.ollama_url = ollama_url or config.llm.ollama_url
        self.validation_errors = []
        self.registry = registry
        
        # Load config
        self.config = self._load_config(config_path)
        self.available_models = self.config.get('llm', {}).get('models', {})
        
        # Set model from config or parameter
        default_model = model or self.config.get('llm', {}).get('default_model', 'mistral')
        self.model = self._get_model_name(default_model)
        self.timeout = config.llm.timeout_seconds
    
    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from YAML file"""
        try:
            config_file = Path(config_path)
            if config_file.exists():
                with open(config_file, 'r') as f:
                    return yaml.safe_load(f) or {}
        except Exception:
            pass
        return {}
    
    def _get_model_name(self, model_key: str) -> str:
        """Get full model name from config or use key directly"""
        if model_key in self.available_models:
            return self.available_models[model_key].get('name', f"{model_key}:latest")
        return model_key if ':' in model_key else f"{model_key}:latest"
    
    def set_model(self, model_key: str) -> bool:
        """Switch to different model"""
        self.model = self._get_model_name(model_key)
        return True
    
    def get_available_models(self) -> Dict:
        """Get list of available models from config"""
        return self.available_models
    
    def generate_plan(self, user_request: str) -> tuple[bool, Optional[ExecutionPlanSchema], Optional[str]]:
        """
        Generate execution plan from user request with retry loop
        Returns: (success, plan, error_message)
        """
        
        self.validation_errors = []
        
        # Get available tools from registry
        tools_description = "filesystem_tool, http_tool, json_tool, shell_tool"
        if self.registry:
            from core.schema_generator import get_tool_descriptions
            tools_description = get_tool_descriptions(self.registry)
        
        # Build prompt with model-specific format
        prompt = self._format_prompt(
            LLM_PROMPT_TEMPLATE.format(
                schema=self.schema,
                tools=tools_description,
                examples=FEW_SHOT_EXAMPLES,
                user_request=user_request
            )
        )
        
        # Retry loop with error feedback
        for attempt in range(self.max_retries):
            try:
                # Call LLM with low temperature for deterministic output
                llm_response = self._call_llm(prompt, temperature=0.1)
                
                if not llm_response:
                    self.validation_errors.append(f"Attempt {attempt+1}: No response from LLM")
                    continue
                
                # Extract JSON from response
                plan_json = self._extract_json(llm_response)
                if not plan_json:
                    self.validation_errors.append(f"Attempt {attempt+1}: Could not extract JSON from response")
                    # Add extraction hint to prompt
                    prompt += "\n\nERROR: Could not parse JSON. Wrap output in ```json fence and ensure valid JSON syntax."
                    continue
                
                # Validate against Pydantic schema
                is_valid, plan, error = validate_plan_json(plan_json)
                
                if is_valid:
                    return True, plan, None
                else:
                    # Log validation error
                    self.validation_errors.append(f"Attempt {attempt+1}: {error}")
                    
                    # Add specific error feedback to prompt
                    prompt += f"\n\nVALIDATION ERROR: {error}\nFix the JSON and retry. Ensure all fields match the schema exactly."
                    
            except Exception as e:
                self.validation_errors.append(f"Attempt {attempt+1}: Exception - {str(e)}")
                if attempt == self.max_retries - 1:
                    error_log = "\n".join(self.validation_errors)
                    return False, None, f"Failed after {self.max_retries} attempts:\n{error_log}"
        
        # All retries exhausted
        error_log = "\n".join(self.validation_errors)
        return False, None, f"Failed to generate valid plan after {self.max_retries} attempts:\n{error_log}"
    
    def generate_response(self, user_message: str, conversation_history: List[Dict[str, str]] = None) -> str:
        """
        Generate conversational response (no structured output)
        Returns: Natural language response
        """
        
        # Build conversational prompt
        system_msg = """You are CUA, an autonomous agent assistant.

Capabilities:
- File operations: read, write, list files
- Task planning and execution
- Answer questions about your abilities

Rules:
- Be concise and direct
- Give actionable responses
- If asked to do a task, suggest using 'plan to...' or specific commands

Respond naturally and helpfully."""
        
        # Build context from history
        messages = []
        if conversation_history:
            for msg in conversation_history[-3:]:
                messages.append(msg)
        messages.append({"role": "user", "content": user_message})
        
        # Format with model-specific prompt
        context = self._format_chat_prompt(system_msg, messages)
        
        # Call LLM for conversational response
        response = self._call_llm(context, temperature=0.7)
        
        return response or "I'm here to help! Ask me anything or give me a task to execute."
    
    def _format_prompt(self, content: str) -> str:
        """Format prompt based on model type"""
        if 'qwen' in self.model.lower():
            # Qwen uses plain format
            return f"{content}\n\n```json\n"
        elif 'mistral' in self.model.lower():
            # Mistral uses instruction format
            return f"<s>[INST] {content} [/INST]\n\n```json\n"
        else:
            # Default plain format
            return f"{content}\n\n```json\n"
    
    def _format_chat_prompt(self, system: str, messages: List[Dict]) -> str:
        """Format chat prompt based on model type"""
        if 'qwen' in self.model.lower():
            # Qwen plain format
            prompt = f"{system}\n\n"
            for msg in messages:
                role = msg.get('role', 'user')
                content = msg.get('content', '')
                if role == 'user':
                    prompt += f"User: {content}\n"
                else:
                    prompt += f"Assistant: {content}\n"
            prompt += "Assistant:"
            return prompt
        elif 'mistral' in self.model.lower():
            # Mistral instruction format
            prompt = f"<s>[INST] {system} [/INST]</s>\n"
            for msg in messages:
                role = msg.get('role', 'user')
                content = msg.get('content', '')
                if role == 'user':
                    prompt += f"[INST] {content} [/INST]"
                else:
                    prompt += f" {content}</s>\n"
            return prompt
        else:
            # Default plain format
            prompt = f"{system}\n\n"
            for msg in messages:
                role = msg.get('role', 'user')
                content = msg.get('content', '')
                prompt += f"{role.title()}: {content}\n"
            return prompt
    
    def _call_llm(self, prompt: str, temperature: float = 0.1) -> Optional[str]:
        """Call Mistral 7B via Ollama with optimized settings"""
        
        try:
            # Optimized for 14B models with 12GB VRAM - maximize context usage
            options = {
                "temperature": temperature,
                "top_p": 0.9,
                "top_k": 40,
                "repeat_penalty": 1.1,
                "num_predict": 8192,  # Max output for 14B model
                "num_ctx": 16384,     # Full 16K context window
                "num_gpu": 99,        # Load ALL layers on GPU
                "num_thread": 8,      # Parallel processing
            }
            
            # Lower temperature for code generation
            if temperature < 0.3:
                options["top_p"] = 0.85
                options["repeat_penalty"] = 1.15
            
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": options,
                    "keep_alive": "10m"  # Keep model loaded longer during orchestration
                },
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("response", "")
            else:
                return None
                
        except requests.exceptions.ConnectionError:
            # Fallback to mock if Ollama not available
            return self._mock_response(prompt, temperature)
        except Exception:
            return None
    
    def _unload_model(self):
        """Unload model from memory immediately"""
        try:
            requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": "",
                    "keep_alive": 0
                },
                timeout=5
            )
        except:
            pass
    
    def _mock_response(self, prompt: str, temperature: float) -> str:
        """Mock response when Ollama unavailable"""
        
        # Check if it's a plan generation request
        if "OUTPUT FORMAT" in prompt and "ExecutionPlan" in prompt:
            mock_response = {
                "plan_id": "plan_001",
                "analysis": "User wants to list files in current directory",
                "steps": [
                    {
                        "step_id": "step_1",
                        "tool": "filesystem_tool",
                        "operation": "list_directory",
                        "parameters": {"path": "."},
                        "reasoning": "List all files in the current working directory"
                    }
                ],
                "confidence": 0.95,
                "estimated_duration": 2
            }
            return json.dumps(mock_response)
        else:
            # Conversational mock
            return "Hello! I'm CUA, an autonomous agent. I can help you with file operations and task execution. Try asking me to 'list files' or 'plan to create a summary'!"
    
    def _extract_json(self, response: str) -> Optional[Dict[str, Any]]:
        """Extract JSON from LLM response with multiple strategies"""
        
        # Strategy 1: Direct parse
        try:
            return json.loads(response.strip())
        except:
            pass
        
        # Strategy 2: Extract from ```json code fence
        if "```json" in response:
            try:
                start = response.find("```json") + 7
                end = response.find("```", start)
                if end != -1:
                    json_str = response[start:end].strip()
                    return json.loads(json_str)
            except:
                pass
        
        # Strategy 3: Extract from generic ``` code fence
        if "```" in response:
            try:
                start = response.find("```") + 3
                # Skip language identifier if present
                newline = response.find("\n", start)
                if newline != -1:
                    start = newline + 1
                end = response.find("```", start)
                if end != -1:
                    json_str = response[start:end].strip()
                    return json.loads(json_str)
            except:
                pass
        
        # Strategy 4: Find JSON object by braces
        try:
            start = response.find("{")
            end = response.rfind("}")
            if start != -1 and end != -1 and end > start:
                json_str = response[start:end+1]
                return json.loads(json_str)
        except:
            pass
        
        return None
