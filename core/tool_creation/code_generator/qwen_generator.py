"""
Qwen-specific code generator with multi-stage LLM generation
Generates code in stages to keep each LLM call under 200 lines for accuracy
"""
import json
import logging
import ast
from typing import Optional, List
from .base import BaseCodeGenerator

logger = logging.getLogger(__name__)


class QwenCodeGenerator(BaseCodeGenerator):
    """Multi-stage generation optimized for local Qwen models"""
    
    def generate(self, template: str, tool_spec: dict) -> Optional[str]:
        """Generate using multi-stage LLM approach: skeleton → handlers one-by-one"""
        from core.tool_creation.validator import ToolValidator
        
        self._creation_id = tool_spec.get('_creation_id')
        correction_prompt = tool_spec.get('_correction_prompt')
        retry_attempt = tool_spec.get('_retry_attempt', 0)
        
        if correction_prompt:
            logger.info(f"Retry attempt {retry_attempt} with correction guidance")
        
        prompt_spec = self._build_prompt_spec(tool_spec)
        contract = self._build_contract_pack()
        
        skeleton = self._generate_stage1_skeleton(prompt_spec, tool_spec, contract, correction_prompt)
        if not skeleton:
            logger.error("Stage 1 skeleton generation failed")
            return None
        
        try:
            if self._creation_id:
                from core.tool_creation_logger import get_tool_creation_logger
                get_tool_creation_logger().log_artifact(self._creation_id, "generated_skeleton", "stage1", skeleton)
        except:
            pass
        
        validator = ToolValidator()
        is_valid, validation_error = validator.validate(skeleton, tool_spec)
        if not is_valid:
            logger.warning(f"Stage 1 skeleton validation failed: {validation_error}")
            return None
        
        final_code = self._generate_stage2_handlers(skeleton, prompt_spec, tool_spec, contract)
        if not final_code:
            logger.error("Stage 2 handler generation failed")
            return None
        
        try:
            if self._creation_id:
                from core.tool_creation_logger import get_tool_creation_logger
                get_tool_creation_logger().log_artifact(self._creation_id, "final_code", "stage2", final_code)
        except:
            pass
        
        is_valid, validation_error = validator.validate(final_code, tool_spec)
        if not is_valid:
            logger.warning(f"Final code validation failed: {validation_error}")
            return None
        
        logger.info("Multi-stage Qwen generation completed successfully")
        return final_code
    
    def _generate_stage1_skeleton(self, prompt_spec: dict, tool_spec: dict, contract: str, correction_prompt: str = None) -> Optional[str]:
        """Stage 1: Generate base skeleton, then add capabilities one by one"""
        tool_name = tool_spec["name"]
        class_name = self._class_name(tool_name)
        operations = prompt_spec.get("inputs", [])
        
        if not operations:
            operations = [{"operation": "execute", "parameters": []}]
        
        base_skeleton = self._generate_base_skeleton(class_name, tool_spec, correction_prompt)
        if not base_skeleton:
            return None
        
        code = base_skeleton
        for op in operations:
            code = self._add_capability_to_skeleton(code, op, class_name, tool_spec)
            if not code:
                return None
        
        return code
    
    def _generate_base_skeleton(self, class_name: str, tool_spec: dict, correction_prompt: str = None) -> Optional[str]:
        """Generate minimal base class structure"""
        prompt = f"""Generate base class structure for: {class_name}

IMPORTS:
from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel

CLASS:
class {class_name}(BaseTool):
    def __init__(self, orchestrator=None):
        self.description = "{tool_spec.get('domain', 'Tool')}"
        self.services = orchestrator.get_services(self.__class__.__name__) if orchestrator else None
        super().__init__()
    
    def register_capabilities(self):
        pass
    
    def execute(self, operation: str, **kwargs):
        raise ValueError(f"Unsupported operation: {{operation}}")

Generate ONLY this base structure.
"""
        
        if correction_prompt:
            prompt = f"{correction_prompt}\n\n{prompt}"
        
        retry_attempt = tool_spec.get('_retry_attempt', 0)
        temperature = 0.2 if retry_attempt > 0 else 0.1
        
        raw = self.llm_client._call_llm(prompt, temperature=temperature, expect_json=False)
        if not raw:
            return None
        
        return self._extract_python_code(raw)
    
    def _add_capability_to_skeleton(self, code: str, operation: dict, class_name: str, tool_spec: dict) -> Optional[str]:
        """Add one capability to existing skeleton"""
        op_name = operation.get("operation", "unknown")
        params = operation.get("parameters", [])
        
        from tools.tool_capability import ParameterType
        valid_types_str = ", ".join([pt.name for pt in ParameterType])
        
        param_details = []
        param_objects = []
        
        type_mapping = {
            'ARRAY': 'LIST', 'DATE': 'STRING', 'DATETIME': 'STRING', 'TIMESTAMP': 'STRING',
            'NUMBER': 'INTEGER', 'FLOAT': 'INTEGER', 'OBJECT': 'DICT', 'JSON': 'DICT',
            'BOOL': 'BOOLEAN', 'PATH': 'FILE_PATH', 'FILEPATH': 'FILE_PATH',
        }
        
        for p in params:
            if isinstance(p, dict):
                p_name = p.get('name', 'param')
                p_type = type_mapping.get(p.get('type', 'string').upper(), p.get('type', 'string').upper())
                p_desc = p.get('description', f'{p_name} parameter')
                p_req = p.get('required', True)
                
                param_details.append(f"  {p_name}: {p_type} ({'required' if p_req else 'optional'}) - {p_desc}")
                param_objects.append(f"Parameter(name='{p_name}', type=ParameterType.{p_type}, description='{p_desc}', required={p_req})")
        
        param_context = "\n".join(param_details) if param_details else "no parameters"
        param_list = ",\n            ".join(param_objects) if param_objects else ""
        
        prompt = f"""TASK: Add capability '{op_name}' to existing class.

CURRENT CODE:
```python
{code}
```

OPERATION TO ADD:
Name: {op_name}
Parameters:
{param_context}

VALID PARAMETER TYPES: {valid_types_str}

Return complete updated code with capability added.
"""
        
        raw = self.llm_client._call_llm(prompt, temperature=0.1, expect_json=False)
        if not raw:
            return None
        
        return self._extract_python_code(raw)
    
    def _generate_stage2_handlers(self, skeleton: str, prompt_spec: dict, tool_spec: dict, contract: str) -> Optional[str]:
        """Stage 2: Implement handlers one by one"""
        code = skeleton
        handler_names = self._extract_handler_names(code, tool_spec)
        
        if not handler_names:
            logger.warning("No handlers found in skeleton")
            return code
        
        for handler_name in handler_names:
            logger.info(f"Generating handler: {handler_name}")
            code = self._generate_single_handler(code, handler_name, prompt_spec, tool_spec, contract)
            if not code:
                logger.error(f"Failed to generate handler: {handler_name}")
                return None
        
        return code
    
    def _extract_handler_names(self, code: str, tool_spec: dict) -> List[str]:
        """Extract handler method names from skeleton"""
        try:
            tree = ast.parse(code)
        except:
            return []
        
        class_name = self._class_name(tool_spec["name"])
        class_node = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name), None)
        if not class_node:
            return []
        
        handlers = []
        for node in class_node.body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith('_handle_'):
                handlers.append(node.name)
        
        return handlers
    
    def _generate_single_handler(self, code: str, handler_name: str, prompt_spec: dict, tool_spec: dict, contract: str) -> Optional[str]:
        """Generate implementation for one handler"""
        op_name = handler_name.replace('_handle_', '')
        
        prompt = f"""Implement handler: {handler_name}

CURRENT CODE:
```python
{code}
```

IMPLEMENT: {handler_name}
Operation: {op_name}

Replace stub with real implementation using self.services.
Return complete updated code.
"""
        
        raw = self.llm_client._call_llm(prompt, temperature=0.2, expect_json=False)
        if not raw:
            return None
        
        return self._extract_python_code(raw)
    
    def _extract_python_code(self, text: str) -> str:
        """Extract Python code from LLM response"""
        if '```python' in text:
            start = text.find('```python') + 9
            end = text.find('```', start)
            return text[start:end].strip()
        elif '```' in text:
            start = text.find('```') + 3
            end = text.find('```', start)
            return text[start:end].strip()
        return text.strip()
    
    def _class_name(self, tool_name: str) -> str:
        """Convert tool name to class name"""
        return ''.join(word.capitalize() for word in tool_name.replace('-', '_').split('_'))
    
    def _build_prompt_spec(self, tool_spec: dict) -> dict:
        """Build prompt specification from tool spec"""
        return {
            "name": tool_spec.get("name", "UnknownTool"),
            "domain": tool_spec.get("domain", "general"),
            "inputs": tool_spec.get("capabilities", []),
            "outputs": tool_spec.get("outputs", {})
        }
    
    def _build_contract_pack(self) -> str:
        """Build contract documentation"""
        return """CUA Tool Contract:
- Inherit from BaseTool
- Implement register_capabilities() and execute()
- Use self.services for external calls
- Return dict results
"""
