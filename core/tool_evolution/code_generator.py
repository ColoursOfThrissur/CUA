"""Qwen-style evolution code generator - preserves structure, improves handlers."""
import ast
import re
import textwrap
from typing import Dict, Any, Optional, List
from core.sqlite_logging import get_logger
from core.enhanced_code_validator import EnhancedCodeValidator

logger = get_logger("code_generator")


class EvolutionCodeGenerator:
    """Generates improved tool code using multi-stage approach."""
    
    def __init__(self, llm_client):
        self.llm = llm_client
    
    def generate_improved_code(
        self, 
        current_code: str, 
        proposal: Dict[str, Any],
        sandbox_error: Optional[str] = None
    ) -> Optional[str]:
        """Generate improved code preserving structure."""
        
        action_type = proposal.get('action_type', 'improve_logic')
        
        # For add_capability, create new handler + register capability
        if action_type == 'add_capability':
            return self._add_new_capability(current_code, proposal, sandbox_error)
        
        # For fix_bug/improve_logic/refactor, modify existing handlers
        return self._improve_existing_handlers(current_code, proposal, sandbox_error)
    
    def _build_service_context(self) -> str:
        """Build grounded service context from EnhancedCodeValidator's registry."""
        registry = EnhancedCodeValidator().service_registry

        nested = {
            "storage": "save(id, data), get(id), list(limit=10), find(query=None, limit=10), count(query=None), update(id, updates), delete(id), exists(id)",
            "llm": "generate(prompt, temperature=0.3, max_tokens=500)",
            "http": "get(url), post(url, data), put(url, data), delete(url), request(method, url, data=None, headers=None)",
            "fs": "read(path), write(path, content), list(path), exists(path), delete(path), mkdir(path)",
            "json": "parse(text), stringify(data, indent=None), query(data, path)",
            "shell": "execute(command)",
            "logging": "info(message), warning(message), error(message), debug(message)",
            "time": "now_utc(), now_local(), now_utc_iso(), now_local_iso()",
            "ids": "generate(prefix=\"\"), uuid()",
            "browser": "open_browser(), navigate(url), find_element(by, value), get_page_text(), take_screenshot(filename), close(), is_available()",
        }
        direct = {
            "call_tool": "call_tool(tool_name, operation, **parameters)",
            "list_tools": "list_tools()",
            "has_capability": "has_capability(capability_name)",
            "detect_language": "detect_language(text)",
            "extract_key_points": "extract_key_points(text, style=\"bullet\", language=\"en\")",
            "sentiment_analysis": "sentiment_analysis(text, language=\"en\")",
            "generate_json_output": "generate_json_output(**kwargs)",
        }

        lines: List[str] = []
        for name in nested:
            if name in registry:
                lines.append(f"- self.services.{name}: {nested[name]}")
        for name in direct:
            if name in registry:
                lines.append(f"- self.services.{direct[name]}")

        lines.append("IMPORTANT: Do not call any self.services.* API not listed above.")
        return "\n".join(lines)

    def _invalid_service_calls(self, code: str) -> List[str]:
        """Detect self.services calls that violate the service registry allowlist."""
        registry = EnhancedCodeValidator().service_registry
        nested_allow = {k: set(v or []) for k, v in registry.items() if isinstance(v, list)}
        direct_allow = {k for k, v in registry.items() if isinstance(v, list) and len(v or []) == 0}

        invalid: List[str] = []

        # Nested calls: self.services.<svc>.<method>(...)
        for svc, method in re.findall(r"self\\.services\\.(\\w+)\\.(\\w+)\\(", code):
            if svc not in nested_allow:
                invalid.append(f"Unknown service self.services.{svc}")
                continue
            allowed = nested_allow.get(svc, set())
            if allowed and method not in allowed:
                invalid.append(f"Unknown method self.services.{svc}.{method}")

        # Direct calls: self.services.<method>(...)
        for name in re.findall(r"self\\.services\\.(\\w+)\\(", code):
            # Avoid double-counting nested (regex doesn't match nested anyway, but be defensive).
            if name in nested_allow and (nested_allow.get(name) and name not in direct_allow):
                continue
            if name not in direct_allow:
                # Also allow nested-service names if the model writes self.services.storage(...) (invalid).
                if name in nested_allow and name not in direct_allow:
                    invalid.append(f"Invalid call self.services.{name}(...) (service requires method like .save/.get)")
                else:
                    invalid.append(f"Unknown ToolServices method self.services.{name}")

        # De-dup while preserving order
        seen = set()
        out = []
        for item in invalid:
            if item not in seen:
                seen.add(item)
                out.append(item)
        return out
    
    def _improve_existing_handlers(
        self,
        current_code: str,
        proposal: Dict[str, Any],
        sandbox_error: Optional[str] = None
    ) -> Optional[str]:
        """Improve existing handlers (fix_bug/improve_logic/refactor)."""
        class_name = self._extract_class_name(current_code)
        if not class_name:
            return None
        
        service_context = self._build_service_context()
        new_services_context = self._build_new_services_context(proposal)
        
        handlers = self._extract_handlers(current_code, class_name)
        if not handlers:
            logger.warning("No handlers found to improve")
            return current_code
        
        improved_code = current_code
        for handler_name, handler_code in handlers.items():
            logger.info(f"Improving handler: {handler_name}")
            improved_handler = self._improve_single_handler(
                handler_code, handler_name, proposal, class_name,
                service_context + new_services_context, sandbox_error
            )
            if improved_handler:
                improved_code = self._replace_handler(improved_code, handler_name, improved_handler, class_name)
        
        return improved_code
    
    def _add_new_capability(
        self,
        current_code: str,
        proposal: Dict[str, Any],
        sandbox_error: Optional[str] = None
    ) -> Optional[str]:
        """Add new capability (new handler + register in capabilities)."""
        class_name = self._extract_class_name(current_code)
        if not class_name:
            logger.error("Cannot add capability: no class name found")
            return None
        
        service_context = self._build_service_context()
        new_services_context = self._build_new_services_context(proposal)
        
        # Generate new handler
        new_handler = self._generate_new_handler(proposal, service_context + new_services_context, sandbox_error)
        if not new_handler:
            logger.error("Cannot add capability: handler generation failed")
            return None
        
        # Insert handler before execute() method
        improved_code = self._insert_handler_before_execute(current_code, new_handler, class_name)
        if not improved_code or len(improved_code) <= len(current_code):
            logger.error("Cannot add capability: handler insertion failed")
            return None
        
        # Update register_capabilities to include new operation
        improved_code = self._add_capability_registration(improved_code, proposal, class_name)
        if not improved_code or len(improved_code) <= len(current_code):
            logger.error("Cannot add capability: capability registration failed")
            return None
        
        # Update execute() method to route to new handler
        improved_code = self._add_execute_routing(improved_code, proposal, class_name)
        if not improved_code or len(improved_code) <= len(current_code):
            logger.error("Cannot add capability: execute routing failed")
            return None
        
        return improved_code
    
    def _build_new_services_context(self, proposal: Dict[str, Any]) -> str:
        """Build context for new services."""
        if not proposal.get('new_service_specs'):
            return ""
        
        context = "\n\nNEW SERVICES TO BE CREATED:\n"
        for svc_name, svc_spec in proposal['new_service_specs'].items():
            context += f"- self.services.{svc_name}: {svc_spec['description']}\n"
            context += f"  Methods: {', '.join(svc_spec['methods'])}\n"
        return context
    
    def _generate_new_handler(
        self,
        proposal: Dict[str, Any],
        service_context: str,
        sandbox_error: Optional[str] = None
    ) -> Optional[str]:
        """Generate new handler method for add_capability."""
        error_context = f"\n\nPREVIOUS ATTEMPT FAILED:\n{sandbox_error}\n" if sandbox_error else ""
        
        # Extract operation name from proposal
        operation_name = self._extract_operation_name(proposal)
        
        prompt = f"""TASK: Create NEW handler method for capability.

CAPABILITY TO ADD:
{proposal['description']}

CHANGES:
{chr(10).join(f"- {c}" for c in proposal['changes'])}

AVAILABLE SERVICES:
{service_context}
{error_context}
CREATE handler method named: _handle_{operation_name}

CRITICAL REQUIREMENTS:
1. Method signature: def _handle_{operation_name}(self, **kwargs) -> dict
2. Extract ALL expected parameters from kwargs:
   - Read the CHANGES list above to identify what parameters this capability needs
   - Use kwargs.get('param_name', default_value) for each parameter
   - Add validation for required parameters (check if None or empty)
3. Use ONLY self.services.X for operations (NEVER self.X directly)
4. Add try-except error handling for all service calls
5. Return plain dict with results (NEVER return ToolResult object)
6. Keep implementation under 20 lines
7. DO NOT reference undefined methods or attributes
8. DO NOT add imports

EXAMPLE STRUCTURE:
def _handle_{operation_name}(self, **kwargs) -> dict:
    # Extract parameters
    param1 = kwargs.get('param1')
    param2 = kwargs.get('param2', default_value)
    
    # Validate required parameters
    if not param1:
        return {{'error': 'Missing required parameter: param1'}}
    
    # Use services with error handling
    try:
        approval_id = self.services.ids.generate("example")
        self.services.storage.save(approval_id, {{'param1': param1, 'param2': param2}})
        return {{'success': True, 'id': approval_id}}
    except Exception as e:
        self.services.logging.error(f"Operation failed: {{e}}")
        return {{'success': False, 'error': str(e)}}

Return ONLY the method definition (no explanations)."""
        
        expected_name = f"_handle_{operation_name}"
        feedback = ""

        for attempt in range(2):
            attempt_prompt = prompt + (f"\n\nVALIDATION FEEDBACK:\n{feedback}\n" if feedback else "")
            try:
                response = self.llm._call_llm(attempt_prompt, temperature=0.2, max_tokens=650, expect_json=False)
                handler = self._extract_python_code(response)
                if not handler or f"def {expected_name}(" not in handler:
                    feedback = "Returned code did not include the required handler method definition with the exact name."
                    continue

                invalid = self._invalid_service_calls(handler)
                if invalid:
                    feedback = "Invalid self.services calls detected:\n- " + "\n- ".join(invalid)
                    continue

                return handler
            except Exception as e:
                logger.warning(f"Failed to generate new handler (attempt {attempt + 1}): {e}")
                feedback = str(e)

        return None
    
    def _extract_operation_name(self, proposal: Dict[str, Any]) -> str:
        """Extract operation name from proposal changes list."""
        # Parse changes list for explicit capability name
        changes = proposal.get('changes', [])
        for change in changes:
            # Look for "Add a new capability named 'X'" or "Create capability 'X'"
            if "capability named" in change.lower():
                # Extract text between quotes
                import re
                match = re.search(r"['\"]([^'\"]+)['\"]", change)
                if match:
                    return match.group(1)
            # Look for "Implement the handler method '_handle_X'"
            if "handler method" in change.lower() and "_handle_" in change:
                match = re.search(r"_handle_(\w+)", change)
                if match:
                    return match.group(1)
        
        # Fallback: parse description (old behavior)
        description = proposal.get('description', '')
        desc_lower = description.lower()
        for keyword in ['add', 'implement', 'create']:
            if keyword in desc_lower:
                words = desc_lower.split()
                if keyword in words:
                    idx = words.index(keyword)
                    if idx + 1 < len(words):
                        return words[idx + 1].replace('capability', '').replace('operation', '').strip()
        
        return description.split()[0].lower() if description else 'unknown'
    
    def _extract_handler_parameters(self, code: str, handler_name: str) -> List[tuple]:
        """Extract parameters from handler by analyzing kwargs.get() calls.
        Returns list of (param_name, is_required) tuples.
        """
        try:
            tree = ast.parse(code)
            
            # Find the handler function
            handler_node = None
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == handler_name:
                    handler_node = node
                    break
            
            if not handler_node:
                return []
            
            params = []
            seen = set()
            
            # Look for kwargs.get('param_name') calls
            for node in ast.walk(handler_node):
                if isinstance(node, ast.Call):
                    # Check if it's kwargs.get()
                    if (isinstance(node.func, ast.Attribute) and 
                        node.func.attr == 'get' and
                        isinstance(node.func.value, ast.Name) and
                        node.func.value.id == 'kwargs'):
                        
                        if node.args and isinstance(node.args[0], ast.Constant):
                            param_name = node.args[0].value
                            if param_name not in seen:
                                # Check if required (no default value or default is None)
                                is_required = len(node.args) == 1 or (
                                    len(node.args) == 2 and 
                                    isinstance(node.args[1], ast.Constant) and 
                                    node.args[1].value is None
                                )
                                params.append((param_name, is_required))
                                seen.add(param_name)
            
            return params
        except Exception as e:
            logger.warning(f"Failed to extract handler parameters: {e}")
            return []
    
    def _insert_handler_before_execute(self, code: str, new_handler: str, class_name: str) -> str:
        """Insert new handler before execute() method."""
        try:
            tree = ast.parse(code)
            class_node = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name), None)
            if not class_node:
                return code
            
            execute_node = next((n for n in class_node.body if isinstance(n, ast.FunctionDef) and n.name == 'execute'), None)
            if not execute_node:
                return code
            
            lines = code.splitlines()
            insert_pos = execute_node.lineno - 1
            
            # Normalize indentation
            normalized = textwrap.dedent(new_handler).strip()
            handler_lines = ["    " + line if line else "" for line in normalized.splitlines()]
            handler_lines.append("")  # Add blank line
            
            lines[insert_pos:insert_pos] = handler_lines
            return "\n".join(lines) + "\n"
        except Exception as e:
            logger.error(f"Failed to insert handler: {e}")
            return code
    
    def _add_capability_registration(self, code: str, proposal: Dict[str, Any], class_name: str) -> str:
        """Add capability registration in register_capabilities."""
        operation_name = self._extract_operation_name(proposal)
        
        # Extract parameters from the generated handler
        handler_params = self._extract_handler_parameters(code, f"_handle_{operation_name}")
        
        # Build parameters list for capability
        if handler_params:
            param_lines = []
            for param_name, is_required in handler_params:
                param_lines.append(
                    f"                Parameter(name='{param_name}', type=ParameterType.STRING, "
                    f"description='{param_name} parameter', required={is_required})"
                )
            params_code = "[\n" + ",\n".join(param_lines) + "\n            ]"
        else:
            params_code = "[]"
        
        # Create ToolCapability registration
        registration = f"""        {operation_name}_capability = ToolCapability(
            name="{operation_name}",
            description="{proposal['description'][:80]}",
            parameters={params_code},
            returns="Operation result",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability({operation_name}_capability, self._handle_{operation_name})"""
        
        # Insert before closing of register_capabilities
        try:
            tree = ast.parse(code)
            class_node = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name), None)
            if not class_node:
                return code
            
            reg_node = next((n for n in class_node.body if isinstance(n, ast.FunctionDef) and n.name == 'register_capabilities'), None)
            if not reg_node:
                return code
            
            lines = code.splitlines()
            insert_pos = reg_node.end_lineno - 1  # Before method end
            
            lines.insert(insert_pos, "")
            lines.insert(insert_pos + 1, registration)
            
            return "\n".join(lines) + "\n"
        except Exception as e:
            logger.error(f"Failed to add capability registration: {e}")
            return code
    
    def _add_execute_routing(self, code: str, proposal: Dict[str, Any], class_name: str) -> str:
        """Add routing in execute() method for new operation."""
        operation_name = self._extract_operation_name(proposal)
        
        try:
            lines = code.splitlines()
            
            # Find the raise ValueError line in execute method
            tree = ast.parse(code)
            class_node = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name), None)
            if not class_node:
                return code
            
            execute_node = next((n for n in class_node.body if isinstance(n, ast.FunctionDef) and n.name == 'execute'), None)
            if not execute_node:
                return code
            
            # Find line with "raise ValueError" within execute method
            raise_line_idx = None
            for i in range(execute_node.lineno - 1, execute_node.end_lineno):
                if i < len(lines) and 'raise ValueError' in lines[i]:
                    raise_line_idx = i
                    break
            
            if raise_line_idx is None:
                return code
            
            # Check indentation of raise line
            raise_indent = len(lines[raise_line_idx]) - len(lines[raise_line_idx].lstrip())
            
            # Insert routing BEFORE raise line with same indentation as raise
            new_if = ' ' * raise_indent + f'if operation == "{operation_name}":'
            new_return = ' ' * (raise_indent + 4) + f'return self._handle_{operation_name}(**kwargs)'
            
            lines.insert(raise_line_idx, new_if)
            lines.insert(raise_line_idx + 1, new_return)
            lines.insert(raise_line_idx + 2, '')  # Blank line before raise
            
            return '\n'.join(lines) + '\n'
        except Exception as e:
            logger.error(f"Failed to add execute routing: {e}")
            return code
    
    def _improve_single_handler(
        self,
        handler_code: str,
        handler_name: str,
        proposal: Dict[str, Any],
        class_name: str,
        service_context: str,
        sandbox_error: Optional[str] = None
    ) -> Optional[str]:
        """Improve a single handler method."""
        
        # Build sandbox error context if this is a retry
        error_context = ""
        if sandbox_error:
            error_context = f"\n\nPREVIOUS ATTEMPT FAILED WITH ERROR:\n{sandbox_error}\n\nFIX THE ERROR ABOVE.\n"
        
        prompt = f"""TASK: Improve this handler method.

CURRENT CODE:
```python
{handler_code}
```

IMPROVEMENT PROPOSAL:
{proposal['description']}

CHANGES TO MAKE:
{chr(10).join(f"- {c}" for c in proposal['changes'])}

AVAILABLE SERVICES (use self.services.X):
{service_context}
{error_context}
CRITICAL REQUIREMENTS:
- Keep method name: {handler_name}
- Keep method signature unchanged
- Preserve all parameters
- ALWAYS use self.services.X - NEVER call self.X directly
- Initialize cache/state in __init__ as self._cache (with underscore)
- Only improve internal logic using AVAILABLE SERVICES above
- DO NOT add parameters to service methods beyond what's listed
- If using NEW SERVICES, they will be created - use exact method signatures shown
- Add error handling if missing
- Keep under 20 lines
- Return plain dict (not ToolResult)
- DO NOT add operations that don't exist in original tool
- DO NOT reference undefined methods or uninitialized attributes
- DO NOT add imports - use only self.services
- Wrap network calls (http, browser) in try-except

Return ONLY the improved method definition."""
        
        feedback = ""
        for attempt in range(3):
            try:
                attempt_prompt = prompt + (f"\n\nVALIDATION FEEDBACK:\n{feedback}\n" if feedback else "")
                response = self.llm._call_llm(attempt_prompt, temperature=0.2, max_tokens=800, expect_json=False)
                improved = self._extract_method_from_response(response, handler_name)
                
                if improved and self._validate_handler(improved, handler_name):
                    invalid = self._invalid_service_calls(improved)
                    if invalid:
                        feedback = "Invalid self.services calls detected:\n- " + "\n- ".join(invalid)
                        continue
                    return improved

                feedback = "Returned code did not contain the exact method definition (name/signature)."
                
            except Exception as e:
                logger.warning(f"Handler improvement attempt {attempt + 1} failed: {e}")
                feedback = str(e)
        
        return None
    
    def _extract_class_name(self, code: str) -> Optional[str]:
        """Extract class name from code."""
        match = re.search(r'class\s+(\w+)', code)
        return match.group(1) if match else None
    
    def _extract_handlers(self, code: str, class_name: str) -> Dict[str, str]:
        """Extract all handler methods from class."""
        try:
            tree = ast.parse(code)
            class_node = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name), None)
            if not class_node:
                return {}
            
            handlers = {}
            lines = code.splitlines()
            
            for node in class_node.body:
                if isinstance(node, ast.FunctionDef):
                    # Get all methods (not just _handle_*)
                    if node.name not in ['__init__', 'register_capabilities', 'get_capabilities', 'execute']:
                        handler_code = "\n".join(lines[node.lineno - 1:node.end_lineno])
                        handlers[node.name] = handler_code
            
            return handlers
        except Exception as e:
            logger.error(f"Failed to extract handlers: {e}")
            return {}
    
    def _extract_method_from_response(self, response: str, method_name: str) -> Optional[str]:
        """Extract method from LLM response."""
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
        
        # Fallback: if response is just the method
        if f"def {method_name}(" in code:
            return code
        
        return None
    
    def _replace_handler(
        self,
        code: str,
        handler_name: str,
        improved_handler: str,
        class_name: str
    ) -> str:
        """Replace handler in class code."""
        try:
            tree = ast.parse(code)
            class_node = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name), None)
            if not class_node:
                return code
            
            target = next((n for n in class_node.body if isinstance(n, ast.FunctionDef) and n.name == handler_name), None)
            if not target:
                return code
            
            # Normalize indentation
            normalized = textwrap.dedent(improved_handler).strip("\n")
            replacement_lines = ["    " + line if line else "" for line in normalized.splitlines()]
            
            lines = code.splitlines()
            start = target.lineno - 1
            end = target.end_lineno
            lines[start:end] = replacement_lines
            
            return "\n".join(lines) + "\n"
        except Exception as e:
            logger.error(f"Failed to replace handler: {e}")
            return code
    
    def _validate_handler(self, handler_code: str, expected_name: str) -> bool:
        """Validate handler code."""
        if not handler_code or len(handler_code) < 10:
            return False
        
        if f"def {expected_name}(" not in handler_code:
            return False
        
        try:
            ast.parse(handler_code)
            return True
        except:
            return False
    
    def _extract_python_code(self, response: str) -> str:
        """Extract Python code from response."""
        if "```python" in response:
            start = response.find("```python") + 9
            end = response.find("```", start)
            return response[start:end].strip()
        elif "```" in response:
            start = response.find("```") + 3
            end = response.find("```", start)
            return response[start:end].strip()
        
        return response.strip()
