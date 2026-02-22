"""
Qwen-specific code generator with multi-stage LLM generation
Generates code in stages to keep each LLM call under 200 lines for accuracy
"""
import json
import logging
import ast
import textwrap
from typing import Optional, List
from .base import BaseCodeGenerator

logger = logging.getLogger(__name__)


class QwenCodeGenerator(BaseCodeGenerator):
    """Multi-stage generation optimized for local Qwen models"""
    
    def generate(self, template: str, tool_spec: dict) -> Optional[str]:
        """Generate using multi-stage LLM approach: skeleton → handlers one-by-one"""
        from core.tool_creation.validator import ToolValidator
        
        # Store creation_id for logging
        self._creation_id = tool_spec.get('_creation_id')
        
        prompt_spec = self._build_prompt_spec(tool_spec)
        contract = self._build_contract_pack()
        
        # Stage 1: Generate skeleton with LLM
        skeleton = self._generate_stage1_skeleton(prompt_spec, tool_spec, contract)
        if not skeleton:
            logger.error("Stage 1 skeleton generation failed")
            return None
        
        # Log skeleton
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
        
        # Stage 2: Implement handlers one by one
        final_code = self._generate_stage2_handlers(skeleton, prompt_spec, tool_spec, contract)
        if not final_code:
            logger.error("Stage 2 handler generation failed")
            return None
        
        # Log final code
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
    
    def _generate_stage1_skeleton(self, prompt_spec: dict, tool_spec: dict, contract: str) -> Optional[str]:
        """Stage 1: Generate base skeleton, then add capabilities one by one"""
        tool_name = tool_spec["name"]
        class_name = self._class_name(tool_name)
        operations = prompt_spec.get("inputs", [])
        
        if not operations:
            operations = [{"operation": "execute", "parameters": []}]
        
        # Step 1a: Generate base class structure
        base_skeleton = self._generate_base_skeleton(class_name, tool_spec)
        if not base_skeleton:
            return None
        
        # Step 1b: Add capabilities one at a time (keeps each LLM call small)
        code = base_skeleton
        for op in operations:
            code = self._add_capability_to_skeleton(code, op, class_name, tool_spec)
            if not code:
                return None
        
        return code
    
    def _generate_base_skeleton(self, class_name: str, tool_spec: dict) -> Optional[str]:
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
        pass  # Will add capabilities next
    
    def execute(self, operation: str, **kwargs):
        raise ValueError(f"Unsupported operation: {{operation}}")

Generate ONLY this base structure.
"""
        
        raw = self.llm_client._call_llm(prompt, temperature=0.1, expect_json=False)
        if not raw:
            return None
        
        return self._extract_python_code(raw)
    
    def _add_capability_to_skeleton(self, code: str, operation: dict, class_name: str, tool_spec: dict) -> Optional[str]:
        """Add one capability to existing skeleton"""
        op_name = operation.get("operation", "unknown")
        params = operation.get("parameters", [])
        
        # Dynamically get valid parameter types
        from tools.tool_capability import ParameterType
        valid_types_str = ", ".join([pt.name for pt in ParameterType])
        
        # Build parameter details with full context
        param_details = []
        param_objects = []
        
        # Map common LLM-generated types to valid ParameterType values
        type_mapping = {
            'ARRAY': 'LIST',
            'DATE': 'STRING',
            'DATETIME': 'STRING',
            'TIMESTAMP': 'STRING',
            'NUMBER': 'INTEGER',
            'FLOAT': 'INTEGER',
            'OBJECT': 'DICT',
            'JSON': 'DICT',
            'BOOL': 'BOOLEAN',
            'PATH': 'FILE_PATH',
            'FILEPATH': 'FILE_PATH',
        }
        
        for p in params:
            if isinstance(p, dict):
                p_name = p.get('name', 'param')
                p_type = p.get('type', 'string').upper()
                # Normalize type to valid ParameterType
                p_type = type_mapping.get(p_type, p_type)
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

VALID PARAMETER TYPES (use ONLY these):
- {valid_types_str}

WHAT TO ADD:

1. In register_capabilities(), add:
```python
{op_name}_capability = ToolCapability(
    name="{op_name}",
    description="{op_name.replace('_', ' ').title()} operation",
    parameters=[
        {param_list}
    ],
    returns="Operation result",
    safety_level=SafetyLevel.LOW,
    examples=[],
    dependencies=[]
)
self.add_capability({op_name}_capability, self._handle_{op_name})
```

2. In execute(), before the raise ValueError line, add:
```python
if operation == "{op_name}":
    return self._handle_{op_name}(**kwargs)
```

3. At end of class, add handler stub:
```python
def _handle_{op_name}(self, **kwargs):
    return {{}}
```

Return complete updated code with these additions.
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
            if isinstance(node, ast.FunctionDef) and node.name.startswith("_handle_"):
                handlers.append(node.name)
        
        return handlers
    
    def _generate_single_handler(self, code: str, handler_name: str, prompt_spec: dict, tool_spec: dict, contract: str) -> Optional[str]:
        """Generate implementation for a single handler method"""
        current_method = self._extract_method(code, tool_spec, handler_name)
        if not current_method:
            return code
        
        op_name = handler_name.replace("_handle_", "")
        operation_info = self._get_operation_info(prompt_spec, op_name)
        
        # Build services list from spec (not hardcoded)
        available_services = tool_spec.get('available_services', [])
        service_methods = tool_spec.get('service_methods', {})
        
        services_list = []
        for service_name in available_services:
            methods = service_methods.get(service_name, '')
            if methods:
                services_list.append(f"{service_name}: {methods}")
        
        # If no services in spec, use minimal defaults
        if not services_list:
            services_list = [
                "storage: save(id, data), get(id), list(limit)",
                "ids: generate(prefix)",
                "time: now_utc()"
            ]
        
        services_context = "\n  * ".join(services_list)
        
        prompt = f"""TASK: Implement handler method.

CURRENT STUB:
```python
{current_method}
```

OPERATION: {op_name}
{operation_info}

CONTEXT:
- Tool has self.services with:
  * {services_context}

{self._get_sandbox_error_context(tool_spec)}

RULES:
- Return plain dict (NOT ToolResult)
- Raise ValueError for validation errors
- Keep under 20 lines
- Use self.services for ALL operations
- ONLY use parameters from kwargs - match spec exactly
- DO NOT create instance variables (self.x) - services maintain state
- DO NOT parse/split parameter values (use as-is)
- If operation has NO parameters, call service method directly
- Wrap browser/http calls in try-except, return {{'success': False, 'error': str(e)}} on failure

EXAMPLE PATTERNS:
- CRUD: item_id = kwargs.get('id') or self.services.ids.generate(); return self.services.storage.save(item_id, dict(kwargs))
- LLM: prompt = f"Analyze: {{kwargs['text']}}"; return {{'result': self.services.llm.generate(prompt, 0.3)}}
- HTTP: try: return self.services.http.get(kwargs['url']); except Exception as e: return {{'success': False, 'error': str(e)}}
- Browser: try: self.services.browser.navigate(kwargs['url']); return {{'success': True, 'text': self.services.browser.get_page_text()}}; except Exception as e: return {{'success': False, 'error': str(e)}}

Return ONLY the method definition. Wrap browser/http/network calls in try-except.
"""
        
        # Log prompt
        try:
            from core.tool_creation_logger import get_tool_creation_logger
            creation_logger = get_tool_creation_logger()
            creation_id = getattr(self, '_creation_id', None)
            if creation_id:
                creation_logger.log_artifact(creation_id, "llm_prompt", f"handler_{handler_name}", prompt)
        except:
            pass
        
        for attempt in range(3):
            raw = self.llm_client._call_llm(prompt, temperature=0.1, expect_json=False)
            
            # Log response
            try:
                if creation_id and raw:
                    creation_logger.log_artifact(creation_id, "llm_response", f"handler_{handler_name}_attempt_{attempt+1}", raw[:2000])
            except:
                pass
            
            if not raw:
                continue
            
            method_code = self._extract_method_from_response(raw, handler_name)
            if not method_code:
                continue
            
            # Enforce handler length by auto-splitting if too long
            method_code = self._enforce_handler_length(method_code, max_lines=20)
            
            merged = self._replace_method(code, tool_spec, handler_name, method_code)
            if merged:
                # Log generated code
                try:
                    if creation_id:
                        creation_logger.log_artifact(creation_id, "generated_handler", handler_name, method_code)
                except:
                    pass
                return merged
        
        logger.warning(f"Failed to generate {handler_name}, keeping stub")
        return code
    
    def _extract_method(self, code: str, tool_spec: dict, method_name: str) -> Optional[str]:
        """Extract method from class code"""
        try:
            tree = ast.parse(code)
            class_name = self._class_name(tool_spec["name"])
            class_node = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name), None)
            if not class_node:
                return None
            
            method_node = next((n for n in class_node.body if isinstance(n, ast.FunctionDef) and n.name == method_name), None)
            if not method_node:
                return None
            
            lines = code.splitlines()
            return "\n".join(lines[method_node.lineno - 1:method_node.end_lineno])
        except:
            return None
    
    def _extract_method_from_response(self, response: str, method_name: str) -> Optional[str]:
        """Extract method from LLM response"""
        code = self._extract_python_code(response)
        if not code:
            return None
        
        code = textwrap.dedent(code).strip()
        
        try:
            tree = ast.parse(code)
            fn = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == method_name), None)
            if fn:
                lines = code.splitlines()
                return "\n".join(lines[fn.lineno - 1:fn.end_lineno])
        except:
            pass
        
        return None
    
    def _replace_method(self, code: str, tool_spec: dict, method_name: str, method_code: str) -> Optional[str]:
        """Replace method in class code"""
        try:
            tree = ast.parse(code)
            class_name = self._class_name(tool_spec["name"])
            class_node = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name), None)
            if not class_node:
                return None
            
            target = next((n for n in class_node.body if isinstance(n, ast.FunctionDef) and n.name == method_name), None)
            if not target:
                return None
            
            normalized = textwrap.dedent(method_code).strip("\n")
            if not normalized.startswith(f"def {method_name}("):
                return None
            
            replacement_lines = ["    " + line if line else "" for line in normalized.splitlines()]
            lines = code.splitlines()
            start = target.lineno - 1
            end = target.end_lineno
            lines[start:end] = replacement_lines
            return "\n".join(lines) + "\n"
        except:
            return None
    
    def _enforce_handler_length(self, handler_code: str, max_lines: int = 20) -> str:
        """Enforce handler length by auto-splitting into helpers if too long"""
        lines = handler_code.splitlines()
        
        # Count non-empty, non-comment lines
        code_lines = [l for l in lines if l.strip() and not l.strip().startswith('#')]
        
        if len(code_lines) <= max_lines:
            return handler_code
        
        logger.warning(f"Handler exceeds {max_lines} lines ({len(code_lines)}), auto-splitting")
        
        # Try to split into helper
        return self._split_into_helper(handler_code)
    
    def _split_into_helper(self, handler_code: str) -> str:
        """Split long handler into main + helper method"""
        try:
            tree = ast.parse(handler_code)
            func = tree.body[0] if tree.body and isinstance(tree.body[0], ast.FunctionDef) else None
            if not func:
                return handler_code
            
            # Find logical split point (after validation, before main logic)
            split_point = self._find_split_point(func)
            if not split_point:
                return handler_code
            
            lines = handler_code.splitlines()
            func_name = func.name
            helper_name = f"{func_name}_impl"
            
            # Split at validation boundary
            validation_lines = lines[:split_point]
            logic_lines = lines[split_point:]
            
            # Build helper method
            helper = f"def {helper_name}(self, **kwargs):\n"
            helper += "\n".join(logic_lines)
            
            # Update main to call helper
            main = "\n".join(validation_lines)
            main += f"\n    return self.{helper_name}(**kwargs)\n"
            
            return main + "\n" + helper
            
        except Exception as e:
            logger.warning(f"Failed to split handler: {e}")
            return handler_code
    
    def _find_split_point(self, func: ast.FunctionDef) -> Optional[int]:
        """Find line to split handler (after validation, before logic)"""
        # Look for validation pattern (if not X: raise ValueError)
        for i, node in enumerate(func.body):
            if isinstance(node, ast.If):
                # Check if it's validation (raises error)
                for child in ast.walk(node):
                    if isinstance(child, ast.Raise):
                        return i + 1  # Split after validation
        
        # Fallback: split at midpoint
        return len(func.body) // 2 if len(func.body) > 2 else None
    
    def _get_sandbox_error_context(self, tool_spec: dict) -> str:
        """Get sandbox error context if this is a retry."""
        error = tool_spec.get('_sandbox_error')
        if error:
            return f"PREVIOUS ATTEMPT FAILED WITH ERROR:\n{error}\n\nFIX THE ERROR ABOVE."
        return ""
    
    def _get_operation_info(self, prompt_spec: dict, op_name: str) -> str:
        """Get operation details from spec"""
        for op in prompt_spec.get("inputs", []):
            if op.get("operation") == op_name:
                params = op.get("parameters", [])
                if not params:
                    return "Parameters: NONE - DO NOT ACCESS kwargs. Call service method directly without parameters."
                param_names = [p.get("name") for p in params if isinstance(p, dict)]
                return f"Parameters: {param_names} (REQUIRED - validate these exist in kwargs)"
        return "Parameters: NONE - DO NOT ACCESS kwargs. Call service method directly without parameters."
    
    def _build_operation_contract(self, operations: List) -> str:
        """Build operation contract text"""
        lines = []
        for op in operations:
            op_name = op.get("operation", "unknown")
            params = op.get("parameters", [])
            param_names = [p.get("name") for p in params if isinstance(p, dict)]
            lines.append(f"- {op_name}: {param_names}")
        return "\n".join(lines)
    
    def _build_contract_pack(self) -> str:
        """Build contract reference"""
        return """Thin Tool Pattern:
- __init__(self, orchestrator=None): self.services = orchestrator.get_services(self.__class__.__name__)
- Handlers return plain dict (orchestrator wraps in ToolResult)
- self.services.storage.save(id, data) / .get(id) / .list(limit=10)
- self.services.llm.generate(prompt, temperature=0.3)
- self.services.http.get(url) / .post(url, data)
- self.services.call_tool(tool_name, operation, **params) - Call another tool
- self.services.list_tools() - List available tools
- self.services.has_capability(name) - Check if capability exists
- Raise ValueError for errors
"""
    
    def _extract_python_code(self, response: str) -> str:
        """Extract Python from markdown fences"""
        import re
        if not response:
            return response
        fenced = re.findall(r"```(?:python)?\s*([\s\S]*?)```", response, flags=re.IGNORECASE)
        return fenced[0].strip() if fenced else response.strip()
    
    def _build_prompt_spec(self, tool_spec: dict) -> dict:
        """Build spec for prompt"""
        return {
            "name": tool_spec.get("name"),
            "domain": tool_spec.get("domain"),
            "inputs": tool_spec.get("inputs", []),
            "outputs": tool_spec.get("outputs", []),
            "dependencies": tool_spec.get("dependencies", []),
            "risk_level": tool_spec.get("risk_level", 0.5),
        }
    
    def _class_name(self, tool_name: str) -> str:
        """Convert tool_name to ClassName"""
        return ''.join((part[:1].upper() + part[1:]) for part in tool_name.split('_') if part)
