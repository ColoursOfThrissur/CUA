"""
LLM Client with model-profile-aware token control and prompt formatting.
"""

import json
import requests
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from core.plan_schema import (
    ExecutionPlanSchema, 
    validate_plan_json, 
    LLM_PROMPT_TEMPLATE,
    PLAN_JSON_SCHEMA,
    FEW_SHOT_EXAMPLES
)

@dataclass
class ModelProfile:
    """
    Per-model-family configuration for token limits, prompt formatting,
    and special instructions. Looked up by model name prefix at call time.
    """
    # Token budgets per call type
    tokens_json: int        # structured JSON output (plans, specs)
    tokens_code: int        # code generation
    tokens_conv: int        # conversational responses
    tokens_min: int         # hard floor — never go below this (thinking models need headroom)

    # Prompt wrapping
    prompt_template: str    # "{content}" | "<s>[INST] {content} [/INST]" | qwen chat format
    json_suffix: str        # appended when expect_json=True
    system_role: str        # "inline" (prepend to prompt) | "separate" (API handles it)

    # Special instructions injected into every system prompt for this model
    special_instructions: str = ""

    def resolve_tokens(self, max_tokens: Optional[int], expect_json: bool, is_code: bool = False) -> int:
        """Return the effective token limit, respecting the hard floor."""
        if max_tokens:
            return max(max_tokens, self.tokens_min)
        base = self.tokens_json if expect_json else (self.tokens_code if is_code else self.tokens_conv)
        return max(base, self.tokens_min)


# --- Profile registry ---
# Key = lowercase prefix of model name. First match wins.
_MODEL_PROFILES: List[tuple] = [
    # Gemini 2.5 thinking models — 65k output cap, give it full room
    ("gemini-2.5", ModelProfile(
        tokens_json=65536, tokens_code=65536, tokens_conv=8192, tokens_min=4096,
        prompt_template="{content}", json_suffix="", system_role="separate",
        special_instructions="Return only valid JSON when asked for JSON. No markdown fences.",
    )),
    # Gemini 1.x / other Gemini — 8k output cap on flash, 32k on pro; use 32k safe ceiling
    ("gemini", ModelProfile(
        tokens_json=32768, tokens_code=32768, tokens_conv=8192, tokens_min=2048,
        prompt_template="{content}", json_suffix="", system_role="separate",
        special_instructions="Return only valid JSON when asked for JSON. No markdown fences.",
    )),
    # OpenAI GPT-4o / GPT-4-turbo — 16k output cap
    ("gpt-4", ModelProfile(
        tokens_json=16384, tokens_code=16384, tokens_conv=4096, tokens_min=1024,
        prompt_template="{content}", json_suffix="", system_role="separate",
    )),
    # OpenAI GPT-3.5 — 4k output cap
    ("gpt-3.5", ModelProfile(
        tokens_json=4096, tokens_code=4096, tokens_conv=2048, tokens_min=512,
        prompt_template="{content}", json_suffix="", system_role="separate",
    )),
    # Qwen (Ollama) — chat template, JSON suffix
    ("qwen", ModelProfile(
        tokens_json=1500, tokens_code=3000, tokens_conv=600, tokens_min=256,
        prompt_template="qwen_chat",  # special marker handled in _apply_profile_format
        json_suffix="\n\nRespond with valid JSON only:",
        system_role="inline",
    )),
    # Mistral (Ollama) — [INST] wrapping
    ("mistral", ModelProfile(
        tokens_json=1200, tokens_code=2000, tokens_conv=512, tokens_min=256,
        prompt_template="<s>[INST] {content} [/INST]",
        json_suffix="\n\n```json\n",
        system_role="inline",
    )),
    # Phi (Ollama) — lightweight, small budgets
    ("phi", ModelProfile(
        tokens_json=800, tokens_code=1200, tokens_conv=400, tokens_min=128,
        prompt_template="{content}", json_suffix="", system_role="inline",
    )),
    # Default fallback
    ("_default", ModelProfile(
        tokens_json=1500, tokens_code=2048, tokens_conv=800, tokens_min=256,
        prompt_template="{content}", json_suffix="", system_role="inline",
    )),
]


def _get_profile(model_name: str) -> ModelProfile:
    """Return the ModelProfile for the given model name (prefix match)."""
    lower = (model_name or "").lower()
    for prefix, profile in _MODEL_PROFILES:
        if prefix == "_default" or lower.startswith(prefix):
            return profile
    return _MODEL_PROFILES[-1][1]  # _default


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
        self.llm_logger = LLMLogger()

        # Response cache for repeated prompts
        self._response_cache = {}
        self._cache_enabled = True

        # Load config
        self.config = self._load_config(config_path)
        self.available_models = self.config.get('llm', {}).get('models', {})

        # Set model from config or parameter
        default_model = model or self.config.get('llm', {}).get('default_model', 'mistral')
        self.model = self._get_model_name(default_model)
        self.timeout = config.llm.timeout_seconds

        # Provider setup
        self.provider = config.llm.provider  # "ollama" | "openai" | "gemini"
        self._api_provider = self._build_api_provider(config)
    
    def _build_api_provider(self, config):
        """Instantiate the correct provider based on config.llm.provider."""
        provider = (config.llm.provider or "ollama").lower()
        api_key = config.llm.api_key or ""
        base_url = config.llm.base_url or ""
        if not api_key and provider in ("openai", "gemini"):
            import logging as _log
            _log.getLogger(__name__).warning(
                f"Provider '{provider}' selected but api_key is empty — falling back to Ollama."
            )
            return None
        if provider == "openai":
            from planner.providers import OpenAIProvider
            return OpenAIProvider(api_key=api_key, model=self.model, base_url=base_url or None, timeout=self.timeout)
        if provider == "gemini":
            from planner.providers import GeminiProvider
            return GeminiProvider(api_key=api_key, model=self.model, timeout=self.timeout)
        return None  # ollama — handled inline

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
            return self.available_models[model_key].get('name', model_key)
        # Only append :latest for Ollama-style model names (not API model names like gemini-*, gpt-*)
        _api_prefixes = ("gemini", "gpt", "claude", "text-", "dall-e")
        if self.provider != "ollama" or any(model_key.startswith(p) for p in _api_prefixes):
            return model_key
        return model_key if ':' in model_key else f"{model_key}:latest"
    
    def set_model(self, model_key: str) -> bool:
        """Switch to different model"""
        self.model = self._get_model_name(model_key)
        return True
    
    def get_available_models(self) -> Dict:
        """Get list of available models from config"""
        return self.available_models
    
    def generate_plan(self, user_request: str, preferred_tools: Optional[List[str]] = None) -> tuple[bool, Optional[ExecutionPlanSchema], Optional[str]]:
        """
        Generate execution plan from user request with retry loop
        Returns: (success, plan, error_message)
        """
        _CORE = {"FilesystemTool", "WebAccessTool", "ShellTool", "JSONTool", "ContextSummarizerTool"}
        self.validation_errors = []
        contracts = self._build_tool_contracts()
        # Filter contracts to preferred tools + core tools when skill context available
        if preferred_tools:
            allowed = set(preferred_tools) | _CORE
            contracts = {k: v for k, v in contracts.items() if k in allowed}
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
    
    def _discover_cua_status(self) -> str:
        """Dynamically discover CUA's current system status and capabilities"""
        status_lines = []
        
        try:
            # Discover tool registry status
            if self.registry:
                tool_count = len(self.registry.tools)
                tool_names = [tool.__class__.__name__ for tool in self.registry.tools]
                status_lines.append(f"Tool Registry: {tool_count} active tools")
                status_lines.append(f"  Core tools: {', '.join(tool_names[:5])}{'...' if len(tool_names) > 5 else ''}")
            
            # Discover skills system status
            try:
                from core.skills import get_skill_registry
                skill_registry = get_skill_registry()
                if skill_registry:
                    skills = skill_registry.list_all()
                    skill_names = [skill.name for skill in skills]
                    status_lines.append(f"Skills System: {len(skills)} skills active")
                    status_lines.append(f"  Skills: {', '.join(skill_names)}")
            except:
                status_lines.append("Skills System: Status unknown")
            
            # Discover improvement systems
            try:
                from core.tool_evolution.flow import ToolEvolutionFlow
                status_lines.append("Tool Evolution: Available")
            except:
                status_lines.append("Tool Evolution: Not available")
            
            try:
                from core.tool_creation.flow import ToolCreationFlow
                status_lines.append("Tool Creation: Available")
            except:
                status_lines.append("Tool Creation: Not available")
            
            # Discover observability systems
            try:
                import os
                db_files = [f for f in os.listdir('data') if f.endswith('.db')]
                status_lines.append(f"Observability: {len(db_files)} databases active")
                status_lines.append(f"  Databases: {', '.join(db_files[:3])}{'...' if len(db_files) > 3 else ''}")
            except:
                status_lines.append("Observability: Status unknown")
            
            # Discover autonomous agent
            try:
                from core.autonomous_agent import AutonomousAgent
                status_lines.append("Autonomous Agent: Available")
            except:
                status_lines.append("Autonomous Agent: Not available")
            
            # Discover memory system
            try:
                from core.memory_system import MemorySystem
                status_lines.append("Memory System: Available")
            except:
                status_lines.append("Memory System: Not available")
            
        except Exception as e:
            status_lines.append(f"System Discovery Error: {str(e)}")
        
        return "\n".join(status_lines) if status_lines else "System status unknown"
    
    def generate_response(self, user_message: str, conversation_history: List[Dict[str, str]] = None) -> str:
        """
        Generate conversational response (no structured output).
        For summary/result messages (no history), uses a lean prompt.
        """
        messages = []
        if conversation_history:
            for msg in (conversation_history or [])[-8:]:
                messages.append(msg)
        messages.append({"role": "user", "content": user_message})

        # Lean path: summary calls pass empty history — skip heavy system prompt
        if not conversation_history:
            context = self._format_chat_prompt("You are a helpful assistant. Answer concisely.", messages)
            conv_tokens = self._get_profile().tokens_conv
            response = self._call_llm(context, temperature=0.7, max_tokens=conv_tokens, expect_json=False)
            return response or "Task completed."

        # Full path: conversational turns need CUA context
        try:
            from core.skills import get_skill_registry
            sk_reg = get_skill_registry()
            skills_info = "\n".join(
                f"- {s.name} ({s.category}): {s.description}"
                for s in (sk_reg.list_all() if sk_reg else [])
            ) or "Skills unavailable"
        except Exception:
            skills_info = "Skills unavailable"

        tool_names = ", ".join(t.__class__.__name__ for t in getattr(self.registry, 'tools', [])) if self.registry else "none"
        profile = self._get_profile()
        system_msg = (
            "You are CUA, a local autonomous agent built on a local LLM. "
            "Never refer to yourself as Qwen, Mistral, or any underlying model. "
            "You are CUA. When asked about your architecture or engine, describe CUA's systems.\n"
            f"Active tools: {tool_names}\n"
            f"Skills:\n{skills_info}\n"
            "Answer based only on your actual capabilities."
            + (f"\n{profile.special_instructions}" if profile.special_instructions else "")
        )
        context = self._format_chat_prompt(system_msg, messages)
        conv_tokens = profile.tokens_conv
        response = self._call_llm(context, temperature=0.7, max_tokens=conv_tokens, expect_json=False)
        return response or "I'm here to help! Ask me anything or give me a task to execute."
    
    def _get_profile(self) -> ModelProfile:
        """Return the ModelProfile for the current model."""
        return _get_profile(self.model)

    def _format_prompt(self, content: str, expect_json: bool = False) -> str:
        """Format a single-turn prompt using the model's profile."""
        if self.provider != "ollama":
            return content  # API providers handle formatting natively
        profile = self._get_profile()
        if profile.prompt_template == "qwen_chat":
            # Qwen uses chat format even for single-turn
            result = f"<|im_start|>user\n{content}<|im_end|>\n<|im_start|>assistant\n"
            return result + (profile.json_suffix if expect_json else "")
        formatted = profile.prompt_template.format(content=content)
        return formatted + (profile.json_suffix if expect_json else "")

    def _format_chat_prompt(self, system: str, messages: List[Dict]) -> str:
        """Format a multi-turn chat prompt using the model's profile."""
        if self.provider != "ollama":
            # API providers: flat concatenation, _call_llm sends as single user message
            parts = [system] if system else []
            for msg in messages:
                parts.append(f"{msg.get('role','user').title()}: {msg.get('content','')}")
            return "\n\n".join(parts)
        profile = self._get_profile()
        if profile.prompt_template == "qwen_chat":
            prompt = f"<|im_start|>system\n{system}<|im_end|>\n"
            for msg in messages:
                prompt += f"<|im_start|>{msg.get('role','user')}\n{msg.get('content','')}" \
                          f"<|im_end|>\n"
            return prompt + "<|im_start|>assistant\n"
        if "[INST]" in profile.prompt_template:
            prompt = f"<s>[INST] {system} [/INST]</s>\n"
            for msg in messages:
                role, content = msg.get('role', 'user'), msg.get('content', '')
                prompt += f"[INST] {content} [/INST]" if role == 'user' else f" {content}</s>\n"
            return prompt
        # Generic fallback
        prompt = f"{system}\n\n"
        for msg in messages:
            prompt += f"{msg.get('role','user').title()}: {msg.get('content','')}\n"
        return prompt
    
    def _call_llm(self, prompt: str, temperature: float = 0.1, max_tokens: int = None, expect_json: bool = False, timeout_override: int = None) -> Optional[str]:
        """Call LLM — routes to API provider (OpenAI/Gemini) or Ollama based on config."""

        from core.logging_system import get_logger
        import hashlib
        logger = get_logger("llm_client")

        # Cache (deterministic calls only)
        cache_key = None
        if self._cache_enabled and temperature < 0.3:
            cache_key = hashlib.md5(f"{prompt}|{temperature}|{max_tokens}|{expect_json}".encode()).hexdigest()
            if cache_key in self._response_cache:
                logger.debug(f"Cache hit for prompt (key={cache_key[:8]}...)")
                return self._response_cache[cache_key]

        logger.info(f"LLM call: provider={self.provider}, model={self.model}, temp={temperature}, expect_json={expect_json}, api_provider={'set' if self._api_provider else 'None'}")

        # --- API provider path ---
        if self._api_provider is not None:
            try:
                profile = self._get_profile()
                resolved_tokens = profile.resolve_tokens(max_tokens, expect_json)
                llm_response = self._api_provider.generate(
                    prompt=prompt,
                    temperature=temperature,
                    max_tokens=resolved_tokens,
                    expect_json=expect_json,
                )
                if llm_response:
                    self.llm_logger.log_interaction(
                        prompt=prompt,
                        response=llm_response,
                        metadata={
                            "model": self.model,
                            "provider": self.provider,
                            "temperature": temperature,
                            "expect_json": expect_json,
                            "status": "success",
                        },
                    )
                    if cache_key:
                        self._response_cache[cache_key] = llm_response
                        if len(self._response_cache) > 100:
                            self._response_cache.pop(next(iter(self._response_cache)))
                return llm_response
            except Exception as e:
                self.llm_logger.log_error(f"API provider error: {str(e)}", {"model": self.model, "provider": self.provider})
                return None

        # --- Ollama path ---
        try:
            profile = self._get_profile()
            num_predict = profile.resolve_tokens(max_tokens, expect_json)
            options = {
                "temperature": temperature,
                "top_p": 0.9,
                "top_k": 40,
                "repeat_penalty": 1.1,
                "num_predict": num_predict,
                "num_ctx": 12288,
                "num_gpu": 99,
                "num_thread": 8,
            }

            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": options,
                "keep_alive": "10m"
            }

            if expect_json:
                payload["format"] = "json"

            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json=payload,
                timeout=timeout_override or self.timeout
            )

            if response.status_code == 200:
                result = response.json()
                llm_response = result.get("response", "")

                # Truncation detection (Ollama/local models only)
                if llm_response and len(llm_response) > 100:
                    last_line = llm_response.strip().split('\n')[-1]
                    if last_line == '```' or last_line.strip().startswith('```'):
                        pass
                    else:
                        truncation_signs = [
                            last_line.endswith(','),
                            last_line.endswith('('),
                            last_line.endswith('['),
                            last_line.endswith('{'),
                            last_line.rstrip().endswith('\\'),
                        ]
                        if any(truncation_signs):
                            logger.error(f"Response truncated. Last line: '{last_line}'")
                            return None

                self.llm_logger.log_interaction(
                    prompt=prompt,
                    response=llm_response,
                    metadata={
                        "model": self.model,
                        "provider": "ollama",
                        "temperature": temperature,
                        "max_tokens": max_tokens or 2048,
                        "expect_json": expect_json,
                        "status": "success",
                        "prompt_length": len(prompt),
                        "response_length": len(llm_response),
                        "tokens_generated": result.get('eval_count', 0),
                        "tokens_prompt": result.get('prompt_eval_count', 0),
                        "cached": False
                    }
                )

                if cache_key:
                    self._response_cache[cache_key] = llm_response
                    if len(self._response_cache) > 100:
                        self._response_cache.pop(next(iter(self._response_cache)))

                return llm_response
            else:
                self.llm_logger.log_error(
                    f"HTTP {response.status_code}",
                    {"model": self.model, "prompt_preview": prompt[:200]}
                )
                return None

        except requests.exceptions.ConnectionError:
            self.llm_logger.log_error("Connection failed - Ollama not available", {"model": self.model})
            return None
        except Exception as e:
            self.llm_logger.log_error(f"Exception: {str(e)}", {"model": self.model, "prompt_preview": prompt[:200]})
            return None
    
    def warmup_model(self):
        """Warm up the model to keep it loaded in memory (Ollama only)."""
        if self.provider != "ollama":
            return True  # No-op for API providers
        from core.logging_system import get_logger
        logger = get_logger("llm_client")
        try:
            logger.info(f"Warming up model: {self.model}")
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": "Hello",
                    "stream": False,
                    "options": {"num_predict": 1},
                    "keep_alive": "30m"
                },
                timeout=60
            )
            if response.status_code == 200:
                logger.info(f"Model {self.model} warmed up successfully")
                return True
            else:
                logger.warning(f"Model warmup returned HTTP {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Failed to warm up model {self.model}: {e}")
            return False
    
    def clear_cache(self):
        """Clear response cache"""
        self._response_cache.clear()
    
    def _unload_model(self):
        """Unload model from memory immediately (Ollama only)."""
        if self.provider != "ollama":
            return  # No-op for API providers
        from core.logging_system import get_logger
        logger = get_logger("llm_client")
        try:
            logger.info(f"Unloading model: {self.model}")
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={"model": self.model, "prompt": "", "keep_alive": 0},
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
        
        # Strategy 4: Find JSON object by braces (most common for plans)
        try:
            start = response.find("{")
            end = response.rfind("}")
            if start != -1 and end != -1 and end > start:
                json_str = response[start:end+1]
                return json.loads(json_str)
        except:
            pass
        
        # Strategy 5: Find JSON array by brackets
        try:
            start = response.find("[")
            end = response.rfind("]")
            if start != -1 and end != -1 and end > start:
                json_str = response[start:end+1]
                return json.loads(json_str)
        except:
            pass
        
        return None
