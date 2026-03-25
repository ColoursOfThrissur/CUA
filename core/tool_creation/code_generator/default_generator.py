"""
Default single-shot code generator
"""
import json
import logging
from typing import Optional
from .base import BaseCodeGenerator

logger = logging.getLogger(__name__)


class DefaultCodeGenerator(BaseCodeGenerator):
    """Single-shot code generation for standard LLMs"""
    
    def generate(self, template: str, tool_spec: dict) -> Optional[str]:
        """Generate tool code in single LLM call with skill-aware enhancement"""
        prompt_spec = self._build_prompt_spec(tool_spec)
        prompt_spec_json = json.dumps(prompt_spec, indent=2)
        operation_contract = self._build_operation_contract(prompt_spec)
        contract_pack = self._build_contract_pack()
        class_name = self._class_name(tool_spec['name'])

        base_prompt = f"""Generate a complete CUA tool class.

Tool spec:
{prompt_spec_json}

Operation contract:
{operation_contract}

Contract reference:
{contract_pack}

Hard requirements:
- Keep the class name exactly: {class_name}
- __init__ must accept orchestrator parameter
- In register_capabilities(), call self.add_capability(...) at least once
- Do NOT assign self.capabilities directly
- Implement execute(self, operation: str, **kwargs)

Return only complete Python code with register_capabilities and execute methods implemented.
"""
        
        # Enhance prompt with skill constraints if available
        enhanced_prompt = base_prompt
        if tool_spec.get("target_skill"):
            try:
                from core.skill_aware_creation import enhance_tool_creation_with_skill
                from core.skills.registry import SkillRegistry
                
                # Get skill definition for enhancement
                skill_registry = SkillRegistry()
                skill_registry.load_all()
                skill_def = skill_registry.get(tool_spec["target_skill"])
                
                if skill_def:
                    enhanced_prompt = enhance_tool_creation_with_skill(
                        base_prompt, skill_def, tool_spec.get("domain", ""), "code"
                    )
                    logger.info(f"Enhanced code generation with {skill_def.name} skill constraints")
            except Exception as e:
                logger.warning(f"Failed to enhance code generation with skill constraints: {e}")
                # Continue with base prompt
        
        return self._generate_with_validation(enhanced_prompt, tool_spec, attempts=3, temperature=0.2)
    
    def _generate_with_validation(self, prompt: str, tool_spec: dict, attempts: int, temperature: float) -> Optional[str]:
        """Generate with validation loop"""
        from core.tool_creation.validator import ToolValidator
        validator = ToolValidator()
        
        feedback = ""
        for _ in range(attempts):
            full_prompt = f"{prompt}\n\n{feedback}" if feedback else prompt
            raw = self.llm_client._call_llm(full_prompt, temperature=temperature, expect_json=False)
            if not raw:
                feedback = "Previous output was empty. Return complete Python code only."
                continue
            
            code = self._extract_python_code(raw)
            is_valid, validation_error = validator.validate(code, tool_spec)
            if is_valid:
                return code
            
            feedback = f"Previous output failed validation.\nIssue: {validation_error}\nFix and return complete code."
            logger.warning(f"Generation retry due to: {validation_error}")
        
        return None
    
    def _extract_python_code(self, response: str) -> str:
        """Extract Python from markdown fences"""
        import re
        if not response:
            return response
        fenced = re.findall(r"```(?:python)?\s*([\s\S]*?)```", response, flags=re.IGNORECASE)
        return fenced[0].strip() if fenced else response.strip()
    
    def _build_prompt_spec(self, tool_spec: dict) -> dict:
        """Build spec for prompt — preserve all skill/gap context."""
        return {
            "name": tool_spec.get("name"),
            "domain": tool_spec.get("domain"),
            "inputs": tool_spec.get("inputs", []),
            "outputs": tool_spec.get("outputs", []),
            "dependencies": tool_spec.get("dependencies", []),
            "risk_level": tool_spec.get("risk_level", 0.5),
            "target_skill": tool_spec.get("target_skill"),
            "target_category": tool_spec.get("target_category"),
            "verification_mode": tool_spec.get("verification_mode"),
            "example_tasks": tool_spec.get("example_tasks", []),
            "example_errors": tool_spec.get("example_errors", []),
            "gap_type": tool_spec.get("gap_type"),
        }
    
    def _build_operation_contract(self, prompt_spec: dict) -> str:
        """Build operation contract text"""
        inputs = prompt_spec.get("inputs", [])
        if not inputs:
            return "- Define at least one operation with explicit parameters."
        
        lines = []
        for op in inputs:
            if isinstance(op, dict):
                op_name = op.get("operation", "<operation>")
                params = op.get("parameters", [])
                if isinstance(params, list):
                    names = [f"{p.get('name')}:{p.get('type')}" for p in params if isinstance(p, dict) and p.get('name')]
                    param_text = ", ".join(names) if names else "no-params"
                else:
                    param_text = "no-params"
                lines.append(f"- {op_name}: {param_text}")
        return "\n".join(lines)
    
    def _build_contract_pack(self) -> str:
        """Build contract reference"""
        from tools.tool_capability import ParameterType
        from core.tool_creation.code_generator.base import TOOL_CREATION_RULES
        valid_types = "|".join([pt.name for pt in ParameterType])
        
        return f"""{TOOL_CREATION_RULES}
Required API contracts:
- Parameter(name=..., type=ParameterType.<{valid_types}>, description=..., required=..., default=...)
- ToolCapability(name=..., description=..., parameters=[...], returns="dict", safety_level=SafetyLevel.<LOW|MEDIUM|HIGH|CRITICAL>, examples=[], dependencies=[])
- self.add_capability(capability_obj, self._handler)
- execute(self, operation: str, **kwargs): return self.execute_capability(operation, **kwargs)

Thin Tool Pattern:
- __init__(self, orchestrator=None): Accept orchestrator, initialize self._cache = {{}} if needed
- Handlers return plain dict with 'success' key (orchestrator wraps in ToolResult)

CRITICAL - ALWAYS use self.services prefix for ALL service calls:
- self.services.storage.save(id, data) / .get(id) / .list(limit=10) - Storage
- self.services.llm.generate(prompt, temperature, max_tokens) - LLM calls
- self.services.http.get/post(url, data) - HTTP requests
- self.services.fs.read/write(path, content) - File operations
- self.services.json.parse/stringify(data) - JSON operations
- self.services.time.now_utc() - Timestamps
- self.services.ids.generate(prefix) - Generate IDs
- self.services.logging.info/warning/error(msg) - Logging
- self.services.detect_language(text) - Detect language
- self.services.extract_key_points(text, style, language) - Extract key points
- self.services.sentiment_analysis(text, language) - Analyze sentiment
- self.services.generate_json_output(**kwargs) - Generate JSON
- self.services.call_tool(tool_name, operation, **params) - Call another tool (public ops only)
- self.services.list_tools() - List available tools
- self.services.has_capability(name) - Check if capability exists

DO NOT:
- Write if/elif chains in execute() - use execute_capability() delegation
- Call self.method_name() for services - ALWAYS use self.services.method_name()
- Use attributes not initialized in __init__
- Reference undefined helper methods
- Raise ValueError for errors - return dict with success=False instead
"""
    
    def _class_name(self, tool_name: str) -> str:
        from core.tool_creation.code_generator.base import canonical_class_name
        return canonical_class_name(tool_name)
