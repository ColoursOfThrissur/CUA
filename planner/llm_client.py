"""
LLM Client with strict schema enforcement
Supports Mistral 7B via Ollama
"""

import json
import requests
import yaml
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from core.plan_schema import (
    ExecutionPlanSchema, 
    validate_plan_json, 
    LLM_PROMPT_TEMPLATE,
    PLAN_JSON_SCHEMA,
    FEW_SHOT_EXAMPLES
)

# Global LLM client instance
_llm_client_instance = None

def get_llm_client(registry=None):
    """Get or create global LLM client instance"""
    global _llm_client_instance
    if _llm_client_instance is None:
        _llm_client_instance = LLMClient(registry=registry)
    return _llm_client_instance

class LLMClient:
    """LLM client with strict schema validation"""
    
    def __init__(self, max_retries: int = None, model: str = None, ollama_url: str = None, config_path: str = "config.yaml", registry=None):
        from core.config_manager import get_config
        from core.llm_logger import LLMLogger
        config = get_config()
        
        self.max_retries = max_retries or config.llm.max_retries
        self.schema = PLAN_JSON_SCHEMA
        self.ollama_url = ollama_url or config.llm.ollama_url
        self.validation_errors = []
        self.registry = registry
        self.llm_logger = LLMLogger()  # Add logger
        
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
        contracts = self._build_tool_contracts()
        tools_description = self._format_tool_contracts_for_prompt(contracts)
        planning_constraints = self._build_planning_constraints(user_request, contracts)
        
        # Build prompt with model-specific format
        prompt = self._format_prompt(
            (
                LLM_PROMPT_TEMPLATE.format(
                schema=self.schema,
                tools=tools_description,
                examples=FEW_SHOT_EXAMPLES,
                user_request=user_request
                )
                + "\n\nADDITIONAL PLANNING CONSTRAINTS:\n"
                + planning_constraints
            ),
            expect_json=True  # Plan generation expects JSON
        )
        
        # Retry loop with error feedback
        for attempt in range(self.max_retries):
            try:
                # Call LLM with low temperature for deterministic output
                llm_response = self._call_llm(prompt, temperature=0.1, expect_json=True)
                
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

                # Normalize common nested parameter shapes against required keys.
                self._normalize_plan_parameters(plan_json, contracts)
                
                # Validate against Pydantic schema
                is_valid, plan, error = validate_plan_json(plan_json)
                
                if is_valid:
                    semantic_ok, semantic_error = self._validate_plan_semantics(
                        plan_json,
                        contracts,
                        user_request=user_request,
                    )
                    if semantic_ok:
                        return True, plan, None
                    self.validation_errors.append(f"Attempt {attempt+1}: {semantic_error}")
                    prompt += (
                        f"\n\nSEMANTIC VALIDATION ERROR: {semantic_error}\n"
                        "Regenerate the full plan. Each step parameters must match the selected tool operation contract exactly."
                    )
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

    def _build_tool_contracts(self) -> Dict[str, Dict[str, Dict[str, List[str]]]]:
        """Build per-tool operation contracts with explicit parameter requirements."""
        contracts: Dict[str, Dict[str, Dict[str, List[str]]]] = {}

        if self.registry:
            for tool in self.registry.tools:
                tool_name = tool.__class__.__name__
                ops: Dict[str, Dict[str, List[str]]] = {}
                for op_name, capability in (tool.get_capabilities() or {}).items():
                    params = [p.name for p in (capability.parameters or [])]
                    required = [p.name for p in (capability.parameters or []) if p.required]
                    ops[op_name] = {"parameters": params, "required": required}
                if ops:
                    contracts[tool_name] = ops

        # Merge in synced registry snapshot (prefer richer op definitions).
        try:
            from core.tool_registry_manager import ToolRegistryManager
            registry_mgr = ToolRegistryManager()
            snapshot = registry_mgr.get_registry().get("tools", {})
            for tool_name, tool_data in snapshot.items():
                ops: Dict[str, Dict[str, List[str]]] = contracts.get(tool_name, {})
                for op_name, op_data in (tool_data.get("operations") or {}).items():
                    params = list(op_data.get("parameters") or [])
                    required = list(op_data.get("required") or [])
                    existing = ops.get(op_name, {"parameters": [], "required": []})
                    existing_params = list(existing.get("parameters") or [])
                    existing_required = list(existing.get("required") or [])

                    # Prefer source with non-empty params/required; merge unique keys.
                    merged_params = existing_params or params
                    if existing_params and params:
                        merged_params = list(dict.fromkeys(existing_params + params))
                    merged_required = existing_required or required
                    if existing_required and required:
                        merged_required = list(dict.fromkeys(existing_required + required))

                    ops[op_name] = {"parameters": merged_params, "required": merged_required}
                if ops:
                    contracts[tool_name] = ops
        except Exception:
            pass

        return contracts

    def _format_tool_contracts_for_prompt(self, contracts: Dict[str, Dict[str, Dict[str, List[str]]]]) -> str:
        """Format contracts for planner prompt with strict parameter-shape guidance."""
        if not contracts:
            return "filesystem_tool, http_tool, json_tool, shell_tool"

        lines: List[str] = []
        for tool_name in sorted(contracts.keys()):
            lines.append(f"{tool_name}:")
            for op_name in sorted(contracts[tool_name].keys()):
                op = contracts[tool_name][op_name]
                params = op.get("parameters", [])
                required = op.get("required", [])
                optional = [p for p in params if p not in required]
                lines.append(f"  - {op_name}")
                lines.append(f"    required: {required}")
                lines.append(f"    optional: {optional}")
                lines.append("    parameters must be a flat object (no nested wrapper keys).")
        return "\n".join(lines)

    def _normalize_plan_parameters(self, plan_json: Dict[str, Any], contracts: Dict[str, Dict[str, Dict[str, List[str]]]]):
        """Normalize common nested shapes like {'contact': {...}} into flat parameter objects."""
        steps = plan_json.get("steps")
        if not isinstance(steps, list):
            return

        for step in steps:
            if not isinstance(step, dict):
                continue
            tool_name = step.get("tool")
            operation = step.get("operation")
            params = step.get("parameters")
            if not isinstance(params, dict):
                continue
            if tool_name not in contracts or operation not in contracts.get(tool_name, {}):
                continue

            required = contracts[tool_name][operation].get("required", [])
            if not required:
                continue

            missing = [r for r in required if r not in params]
            if not missing:
                continue

            # Flatten single nested object if it contains the required keys.
            nested_dicts = [v for v in params.values() if isinstance(v, dict)]
            if len(nested_dicts) == 1:
                nested = nested_dicts[0]
                if all(r in nested for r in required):
                    merged = dict(nested)
                    for k, v in params.items():
                        if not isinstance(v, dict):
                            merged[k] = v
                    step["parameters"] = merged

    def _validate_plan_semantics(
        self,
        plan_json: Dict[str, Any],
        contracts: Dict[str, Dict[str, Dict[str, List[str]]]],
        user_request: str = "",
    ) -> Tuple[bool, str]:
        """Validate tool/operation existence and required parameter presence."""
        if not contracts:
            return True, ""

        steps = plan_json.get("steps")
        if not isinstance(steps, list):
            return False, "Plan JSON missing 'steps' list"

        for idx, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                return False, f"Step {idx} is not an object"

            tool_name = step.get("tool")
            operation = step.get("operation")
            params = step.get("parameters", {})

            if tool_name not in contracts:
                return False, f"Step {idx}: unknown tool '{tool_name}'"
            if operation not in contracts[tool_name]:
                return False, f"Step {idx}: unknown operation '{operation}' for tool '{tool_name}'"
            if not isinstance(params, dict):
                return False, f"Step {idx}: parameters must be an object"

            required = contracts[tool_name][operation].get("required", [])
            missing = [name for name in required if name not in params]
            if missing:
                return False, (
                    f"Step {idx}: missing required parameters {missing} "
                    f"for {tool_name}.{operation}"
                )

            # Guardrail: reject placeholder/external HTTP plans when user did not provide a URL.
            tool_lc = str(tool_name).lower()
            if "http" in tool_lc:
                url = str(params.get("url", "")).strip().lower()
                if "example.com" in url:
                    return False, (
                        f"Step {idx}: placeholder URL '{params.get('url')}' is not allowed. "
                        "Use real user-provided URLs or non-HTTP tools."
                    )
                if url and not self._request_contains_url(user_request):
                    return False, (
                        f"Step {idx}: HTTP operation {tool_name}.{operation} requires a URL in user request. "
                        "User request did not provide one."
                    )

        return True, ""

    @staticmethod
    def _request_contains_url(user_request: str) -> bool:
        text = (user_request or "").lower()
        return "http://" in text or "https://" in text

    def _build_planning_constraints(
        self,
        user_request: str,
        contracts: Dict[str, Dict[str, Dict[str, List[str]]]],
    ) -> str:
        """Build strict runtime constraints to reduce hallucinated plans."""
        lines: List[str] = [
            "- Use only tool names and operations listed in AVAILABLE TOOLS.",
            "- Do not invent external APIs, domains, or endpoints.",
            "- Do not use placeholder URLs like api.example.com or example.com.",
            "- If user request has no URL, do not use HTTP tools.",
            "- Parameters must be flat object keys matching operation contracts."
        ]

        request_text = (user_request or "").lower()
        preferred: List[str] = []
        for tool_name, ops in contracts.items():
            op_create = ops.get("create", {})
            if "contact_id" in [p.lower() for p in op_create.get("parameters", [])]:
                preferred.append(tool_name)

        if "contact_id" in request_text and preferred:
            lines.append(
                f"- For contact_id-style local CRUD requests, prefer these tools first: {preferred}."
            )
            lines.append(
                "- Build steps in create -> get -> list order when user explicitly asks this sequence."
            )

        return "\n".join(lines)
    
    def generate_response(self, user_message: str, conversation_history: List[Dict[str, str]] = None) -> str:
        """
        Generate conversational response (no structured output)
        Returns: Natural language response
        """
        
        # Get tool capabilities from registry file if available
        tools_info = "No tools available"
        try:
            from core.tool_registry_manager import ToolRegistryManager
            registry_mgr = ToolRegistryManager()
            tools_info = registry_mgr.get_all_capabilities_text()
        except:
            # Fallback to direct registry query
            if self.registry:
                tools_list = []
                for tool in self.registry.tools:
                    caps = tool.get_capabilities()
                    ops = ", ".join(sorted(caps.keys()))
                    tool_name = getattr(tool, "name", tool.__class__.__name__)
                    tools_list.append(f"- {tool_name}: {ops}")
                tools_info = "\n".join(tools_list)
        
        # Build conversational prompt
        system_msg = f"""You are CUA, an autonomous agent assistant.

Your available tools and capabilities:
{tools_info}

Rules:
- Be concise and helpful
- If asked what you can do, explain your tools
- If asked to perform a task, tell user you can execute it
- Be conversational and friendly

Respond naturally."""
        
        # Build context from history
        messages = []
        if conversation_history:
            for msg in conversation_history[-3:]:
                messages.append(msg)
        messages.append({"role": "user", "content": user_message})
        
        # Format with model-specific prompt
        context = self._format_chat_prompt(system_msg, messages)
        
        # Call LLM for conversational response
        response = self._call_llm(context, temperature=0.7, expect_json=False)
        
        return response or "I'm here to help! Ask me anything or give me a task to execute."
    
    def _format_prompt(self, content: str, expect_json: bool = False) -> str:
        """Format prompt based on model type"""
        if 'qwen' in self.model.lower():
            # Qwen: Plain format with explicit JSON instruction when needed
            if expect_json:
                return f"{content}\n\nRespond with valid JSON only:"
            return content
        elif 'mistral' in self.model.lower():
            # Mistral uses instruction format
            json_hint = "\n\n```json\n" if expect_json else ""
            return f"<s>[INST] {content} [/INST]{json_hint}"
        else:
            # Default plain format
            return content
    
    def _format_chat_prompt(self, system: str, messages: List[Dict]) -> str:
        """Format chat prompt based on model type"""
        if 'qwen' in self.model.lower():
            # Qwen: Use <|im_start|> format for better instruction following
            prompt = f"<|im_start|>system\n{system}<|im_end|>\n"
            for msg in messages:
                role = msg.get('role', 'user')
                content = msg.get('content', '')
                prompt += f"<|im_start|>{role}\n{content}<|im_end|>\n"
            prompt += "<|im_start|>assistant\n"
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
    
    def _call_llm(self, prompt: str, temperature: float = 0.1, max_tokens: int = None, expect_json: bool = False) -> Optional[str]:
        """Call Mistral 7B via Ollama with structured output enforcement"""
        
        from core.logging_system import get_logger
        logger = get_logger("llm_client")
        
        logger.debug(f"LLM call: model={self.model}, temp={temperature}, expect_json={expect_json}")
        
        try:
            options = {
                "temperature": temperature,
                "top_p": 0.9,
                "top_k": 40,
                "repeat_penalty": 1.1,
                "num_predict": max_tokens or 2048,
                "num_ctx": 8192,
                "num_gpu": 99,
                "num_thread": 8,
            }
            
            # Enforce JSON format for structured outputs
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": options,
                "keep_alive": "10m"
            }
            
            if expect_json:
                payload["format"] = "json"  # Ollama JSON mode
            
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json=payload,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                llm_response = result.get("response", "")
                
                # CRITICAL: Detect truncated response
                if llm_response and len(llm_response) > 100:
                    # Check if response ends abruptly (not at natural boundary)
                    last_line = llm_response.strip().split('\n')[-1]
                    
                    # ONLY flag as truncated if it ends mid-code (not at closing fence)
                    if last_line == '```':
                        # This is a NORMAL code block ending - NOT truncated
                        pass
                    elif last_line.strip().startswith('```'):
                        # Closing fence with language - also normal
                        pass
                    else:
                        # Check for actual truncation indicators
                        truncation_signs = [
                            last_line.endswith(','),  # Ends with comma
                            last_line.endswith('('),  # Unclosed paren
                            last_line.endswith('['),  # Unclosed bracket
                            last_line.endswith('{'),  # Unclosed brace
                            last_line.rstrip().endswith('\\'),  # Line continuation
                        ]
                        
                        if any(truncation_signs):
                            logger.error(f"Response truncated. Last line: '{last_line}'")
                            logger.error(f"Response length: {len(llm_response)} chars, tokens: {result.get('eval_count', 0)}")
                            logger.debug(f"Full response: {llm_response}")
                            # Return None to trigger retry with error feedback
                            return None
                
                # Log interaction with detailed metadata
                self.llm_logger.log_interaction(
                    prompt=prompt,  # Full prompt for debugging
                    response=llm_response,  # Full response
                    metadata={
                        "model": self.model,
                        "temperature": temperature,
                        "max_tokens": max_tokens or 2048,
                        "expect_json": expect_json,
                        "status": "success",
                        "prompt_length": len(prompt),
                        "response_length": len(llm_response),
                        "tokens_generated": result.get('eval_count', 0),
                        "tokens_prompt": result.get('prompt_eval_count', 0),
                        "prompt_ends_with": prompt[-100:] if len(prompt) > 100 else prompt,
                        "response_ends_with": llm_response[-100:] if len(llm_response) > 100 else llm_response
                    }
                )
                
                return llm_response
            else:
                self.llm_logger.log_error(
                    f"HTTP {response.status_code}",
                    {"model": self.model, "prompt_preview": prompt[:200]}
                )
                return None
                
        except requests.exceptions.ConnectionError:
            self.llm_logger.log_error(
                "Connection failed - Ollama not available",
                {"model": self.model}
            )
            return None
        except Exception as e:
            self.llm_logger.log_error(
                f"Exception: {str(e)}",
                {"model": self.model, "prompt_preview": prompt[:200]}
            )
            return None
    
    def _unload_model(self):
        """Unload model from memory immediately"""
        from core.logging_system import get_logger
        logger = get_logger("llm_client")
        
        try:
            logger.info(f"Unloading model: {self.model}")
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": "",
                    "keep_alive": 0
                },
                timeout=5
            )
            if response.status_code == 200:
                logger.info(f"Model {self.model} unloaded successfully")
            else:
                logger.warning(f"Model unload returned HTTP {response.status_code}")
        except Exception as e:
            logger.error(f"Failed to unload model {self.model}: {e}")
    
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
        
        # Strategy 4: Find JSON array by brackets
        try:
            start = response.find("[")
            end = response.rfind("]")
            if start != -1 and end != -1 and end > start:
                json_str = response[start:end+1]
                return json.loads(json_str)
        except:
            pass
        
        # Strategy 5: Find JSON object by braces
        try:
            start = response.find("{")
            end = response.rfind("}")
            if start != -1 and end != -1 and end > start:
                json_str = response[start:end+1]
                return json.loads(json_str)
        except:
            pass
        
        return None
