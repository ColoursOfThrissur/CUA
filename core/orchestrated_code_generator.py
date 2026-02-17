"""
Orchestrated Code Generator - Multi-step approach for small LLMs
Breaks complex code generation into manageable steps
"""
import json
from typing import Dict, List, Optional, Tuple
from core.method_extractor import MethodExtractor
from core.code_integrator import CodeIntegrator

class OrchestratedCodeGenerator:
    def __init__(self, llm_client, analyzer):
        from core.config_manager import get_config
        self.config = get_config()
        self.llm_client = llm_client
        self.analyzer = analyzer
        self.extractor = MethodExtractor()
        self.integrator = CodeIntegrator()
    
    def generate_code(self, user_request: str, target_file: str, target_tool: Optional[str] = None, previous_errors: Optional[List[str]] = None) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Generate code using multi-step orchestration
        Args:
            user_request: What to generate
            target_file: File to create/modify
            target_tool: For test files, the tool being tested
        Returns: (success, complete_code, error_message)
        """
        
        if not target_file:
            return False, None, "No target file specified"
        
        from core.logging_system import get_logger
        logger = get_logger("code_generator")
        
        # Warmup: ensure model is loaded on GPU before orchestration
        if self.config.improvement.warmup_enabled:
            logger.info("Loading model to GPU...")
            self.llm_client._call_llm("Ready", temperature=0.1)
        
        logger.info(f"Planning modifications for {target_file}...")
        plan = self._plan_modifications(user_request, target_file)
        if not plan:
            return False, None, "Failed to create modification plan"
        
        logger.debug(f"Plan: {json.dumps(plan, indent=2)}")
        
        modified_methods = {}
        new_methods = {}
        
        for method_name in plan.get('methods_to_modify', []):
            logger.info(f"Modifying method: {method_name}")
            success, code = self._generate_method(method_name, target_file, user_request, plan)
            if success:
                logger.info(f"Generated {method_name} ({len(code)} chars)")
                modified_methods[method_name] = code
            else:
                logger.error(f"Failed to generate {method_name}")
                # Return the failed code for self-correction attempt
                error_msg = f"Failed to generate method: {method_name}"
                if code:
                    error_msg += " - validation failed"
                return False, code, error_msg
        
        for method_name in plan.get('new_methods', []):
            logger.info(f"Creating new method: {method_name}")
            success, code = self._generate_new_method(method_name, target_file, user_request, plan, target_tool, previous_errors or [])
            if success:
                logger.info(f"Generated {method_name} ({len(code)} chars)")
                new_methods[method_name] = code
            else:
                logger.error(f"Failed to generate {method_name}")
                return False, None, f"Failed to generate new method: {method_name}"
        
        logger.info("Integrating changes...")
        original_code = self.analyzer.get_file_content(target_file)
        
        # If new file (test file), use generated code directly
        if not original_code:
            if new_methods:
                # For new test files, return the complete generated code
                result_code = list(new_methods.values())[0]
                logger.info(f"Created new file with {len(result_code)} chars")
            else:
                return False, None, "No code generated for new file"
        else:
            # Existing file - integrate changes
            result_code = original_code
            if modified_methods:
                result_code = self.integrator.integrate_methods(result_code, modified_methods)
                logger.info(f"Integrated {len(modified_methods)} modified methods")
            if new_methods:
                result_code = self.integrator.add_new_methods(result_code, new_methods)
                logger.info(f"Added {len(new_methods)} new methods")
        
        # Clean trailing placeholders
        lines = result_code.split('\n')
        while lines:
            last_line = lines[-1].strip().lower()
            if not last_line or 'rest of' in last_line or 'remains unchanged' in last_line:
                lines.pop()
            else:
                break
        result_code = '\n'.join(lines)
        
        logger.info("Validating complete code...")
        validation_result = self._validate_complete_code(result_code)
        if not validation_result:
            logger.error("Validation failed")
            logger.debug(f"Last 500 chars:\n{result_code[-500:]}")
            # Return broken code with error for self-correction, but mark as failed
            return False, result_code, "Validation failed: indentation or syntax error"
        
        logger.info("Validation passed")
        return True, result_code, None
    
    def _plan_modifications(self, user_request: str, target_file: str) -> Optional[Dict]:
        """Step 1: Plan which methods to modify/add"""
        
        # Get file structure (signatures only, not full code)
        original_code = self.analyzer.get_file_content(target_file)
        
        # For new files (like test files), skip planning and go straight to generation
        if not original_code:
            # New file - return simple plan to generate complete file
            return {
                "methods_to_modify": [],
                "new_methods": ["complete_file"],  # Placeholder name
                "reason": "Creating new file"
            }
        
        methods = self.extractor.extract_methods(original_code)
        method_signatures = {name: info['args'] for name, info in methods.items()}
        
        prompt = self.llm_client._format_prompt(f"""Analyze this modification request and create a plan.

USER REQUEST: {user_request}
TARGET FILE: {target_file}

EXISTING METHODS:
{json.dumps(method_signatures, indent=2)}

OUTPUT JSON with:
{{
  "methods_to_modify": ["method1", "method2"],
  "new_methods": ["new_method1"],
  "reason": "explanation"
}}

Respond with JSON only:""")
        
        response = self.llm_client._call_llm(prompt, temperature=0.2)
        if not response:
            return None
        
        plan = self.llm_client._extract_json(response)
        return plan
    
    def _generate_method(self, method_name: str, target_file: str, user_request: str, plan: Dict) -> Tuple[bool, Optional[str]]:
        """Step 2a: Generate single modified method"""
        
        original_code = self.analyzer.get_file_content(target_file)
        methods = self.extractor.extract_methods(original_code)
        
        if method_name not in methods:
            return False, None
        
        method_info = methods[method_name]
        current_code = method_info['code']
        
        # Get dependencies
        deps = self.extractor.get_method_dependencies(method_name, original_code)
        dep_code = ""
        for dep in deps:
            if dep in methods:
                dep_code += f"\n# Dependency: {dep}\n{methods[dep]['code']}\n"
        
        prompt = self.llm_client._format_prompt(f"""Modify this method based on user request.

USER REQUEST: {user_request}
REASON: {plan.get('reason', '')}

CURRENT METHOD:
```python
{current_code}
```

DEPENDENCIES:
```python
{dep_code}
```

IMPORTANT RULES:
1. Output COMPLETE method code - no placeholders
2. Keep method signature EXACTLY the same
3. NO comments like "# rest unchanged" or "# existing code"
4. Must have proper return statement
5. NO async/await unless method already uses it
6. Complete working code only
7. If you can't implement fully, return the original code unchanged
8. CRITICAL: Maintain proper indentation - all code inside method must be indented consistently
9. Do NOT mix tabs and spaces - use 4 spaces for indentation

Output the COMPLETE modified method:""")
        
        last_code = None
        for attempt in range(3):
            response = self.llm_client._call_llm(prompt, temperature=0.2)
            if not response:
                continue
            
            code = self._extract_code(response)
            last_code = code  # Save for potential return
            
            if code and self._validate_method(code, method_name):
                return True, code
            
            # If validation failed, give specific feedback
            if code:
                if 'return' not in code and method_name != '__init__':
                    prompt += f"\n\nERROR: Method must have a return statement. Add: return <value>\n"
                elif 'async def' in code and 'async def' not in current_code:
                    prompt += f"\n\nERROR: Do NOT add async. Keep method synchronous like original.\n"
                elif '\t' in code:
                    prompt += f"\n\nERROR: Do NOT use tabs. Use 4 spaces for indentation.\n"
                else:
                    prompt += f"\n\nERROR: Method incomplete, invalid indentation, or syntax error. Output COMPLETE working code with proper 4-space indentation.\n"
            else:
                prompt += f"\n\nERROR: Could not extract code. Use ```python code ``` format.\n"
        
        # Return last generated code even if failed, for self-correction
        return False, last_code
    
    def _generate_new_method(self, method_name: str, target_file: str, user_request: str, plan: Dict, target_tool: Optional[str] = None, previous_errors: Optional[List[str]] = None) -> Tuple[bool, Optional[str]]:
        """Step 2b: Generate new method or complete test file"""
        
        original_code = self.analyzer.get_file_content(target_file)
        
        # If creating new test file, generate complete file
        if not original_code and 'test_' in target_file:
            return self._generate_complete_test_file(target_file, user_request, plan, target_tool, previous_errors or [])
        
        class_def = self.extractor.extract_class_definition(original_code) if original_code else ""
        
        prompt = self.llm_client._format_prompt(f"""Create a new method for this class.

USER REQUEST: {user_request}
METHOD NAME: {method_name}
REASON: {plan.get('reason', '')}

CLASS CONTEXT:
```python
{class_def}
```

RULES:
1. Output COMPLETE method code
2. Use def {method_name}(self, ...):
3. Must have return statement
4. NO placeholders
5. Complete working code only

Output the COMPLETE new method:""")
        
        for attempt in range(3):
            response = self.llm_client._call_llm(prompt, temperature=0.2)
            if not response:
                continue
            
            code = self._extract_code(response)
            if code and self._validate_method(code, method_name):
                return True, code
            
            prompt += f"\n\nERROR: Method incomplete. Must have return statement.\n"
        
        return False, None
    
    def _generate_complete_test_file(self, target_file: str, user_request: str, plan: Dict, target_tool: Optional[str] = None, previous_errors: Optional[List[str]] = None) -> Tuple[bool, Optional[str]]:
        """Generate complete test file for new tests"""
        
        # Extract tool name from test file path or use provided target_tool
        if target_tool:
            tool_file = target_tool
            tool_name = tool_file.replace('tools/', '').replace('.py', '')
        else:
            tool_name = target_file.replace('tests/unit/test_', '').replace('.py', '')
            tool_file = f"tools/{tool_name}.py"
        
        # Get tool code
        tool_code = self.analyzer.get_file_content(tool_file)
        if not tool_code:
            return False, None
        
        # Extract class name from tool code
        import re
        class_match = re.search(r'class (\w+)', tool_code)
        class_name = class_match.group(1) if class_match else "ToolClass"
        
        # Build error context if available
        error_context = ""
        if previous_errors:
            error_context = "\n\nPREVIOUS ERRORS TO AVOID:\n"
            for err in previous_errors[-3:]:
                error_context += f"- {err}\n"
        
        prompt = self.llm_client._format_prompt(f"""Create a COMPLETE test file.

USER REQUEST: {user_request}
TEST FILE: {target_file}
TOOL FILE: {tool_file}
TOOL CLASS: {class_name}

TOOL CODE:
```python
{tool_code[:self.config.improvement.code_preview_chars]}
```
{error_context}

!! CRITICAL - READ THIS CAREFULLY !!

WRONG PATTERN (DO NOT USE):
```python
# WRONG - ToolResult has NO execute method
result = ToolResult(...)
result.execute()  # ERROR: This will fail!
```

CORRECT PATTERN (USE THIS):
```python
# CORRECT - Call execute on the TOOL, not the result
tool = {class_name}()
result = tool.execute("operation", {{"param": "value"}})
assert result.status == ResultStatus.SUCCESS
```

RULES:
1. Import: from tools.{tool_name} import {class_name}
2. Import: from tools.tool_result import ToolResult, ResultStatus
3. Create instance: tool = {class_name}()
4. Call tool.execute() NOT result.execute()
5. ToolResult is the RETURN VALUE - it has NO execute method
6. Check: result.status and result.data
7. Use pytest: def test_name():
8. NO unittest classes

REMEMBER: tool.execute() returns ToolResult. You check the result, not call execute on it.

Output COMPLETE test file:""")
        
        for attempt in range(3):
            response = self.llm_client._call_llm(prompt, temperature=0.2)
            if not response:
                continue
            
            # Log the response for debugging
            from core.llm_logger import LLMLogger
            logger = LLMLogger()
            preview_len = min(500, len(prompt))
            logger.log_interaction(
                prompt=prompt[:preview_len],
                response=response,
                metadata={"phase": "test_generation", "attempt": attempt, "target_file": target_file}
            )
            
            code = self._extract_code(response)
            if code and 'def test_' in code and 'import' in code:
                # Auto-fix common mistake: result.execute() -> tool.execute()
                if 'result.execute(' in code:
                    logger.info("Auto-fixing result.execute() to tool.execute()")
                    code = code.replace('result.execute(', 'tool.execute(')
                return True, code
            
            prompt += f"\n\nERROR: Must be complete test file with imports and test functions.\n"
        
        return False, None
    
    def _extract_code(self, response: str) -> Optional[str]:
        """Extract code from LLM response and clean placeholders"""
        code = None
        
        if '```python' in response:
            start = response.find('```python') + 9
            end = response.find('```', start)
            if end != -1:
                code = response[start:end].strip()
        
        elif '```' in response:
            start = response.find('```') + 3
            newline = response.find('\n', start)
            if newline != -1:
                start = newline + 1
            end = response.find('```', start)
            if end != -1:
                code = response[start:end].strip()
        
        if code:
            # Remove placeholder comments
            lines = code.split('\n')
            cleaned = []
            for line in lines:
                lower = line.lower().strip()
                if 'rest of' in lower or 'remains unchanged' in lower or 'existing code' in lower:
                    continue
                cleaned.append(line)
            code = '\n'.join(cleaned)
        
        return code
    
    def _validate_method(self, code: str, method_name: str) -> bool:
        """Validate single method is complete"""
        
        # Must have method definition
        if f'def {method_name}' not in code:
            return False
        
        # Must have return statement (unless __init__)
        if method_name != '__init__' and 'return' not in code:
            return False
        
        # No placeholders
        if '# rest' in code.lower() or 'unchanged' in code.lower():
            return False
        
        if '...' in code or 'pass  #' in code:
            return False
        
        # Valid syntax
        try:
            import ast
            ast.parse(code)
        except:
            return False
        
        return True
    
    def _validate_complete_code(self, code: str) -> bool:
        """Validate complete file and clean trailing placeholders"""
        
        # Remove trailing placeholder comments
        lines = code.split('\n')
        while lines:
            last_line = lines[-1].strip().lower()
            if not last_line or 'rest of' in last_line or 'remains unchanged' in last_line:
                lines.pop()
            else:
                break
        
        code = '\n'.join(lines)
        
        # Check for incomplete return statements
        if 'return"' in code or 'return\'' in code:
            logger.debug("Found incomplete return statement")
            return False
        
        # Check for mismatched braces/brackets
        if code.count('{') != code.count('}'):
            logger.debug("Mismatched braces")
            return False
        
        # No placeholders in middle
        if '# The rest' in code or 'remains unchanged' in code:
            return False
        
        # Check for placeholder imports
        if 'from your_module import' in code or '# Replace with actual' in code:
            logger.debug("Found placeholder imports")
            return False
        
        # Check for common indentation errors that cause "unexpected indent"
        import re
        # Look for lines that start with unexpected indentation after dedent
        prev_indent = 0
        for i, line in enumerate(lines, 1):
            if not line.strip():
                continue
            curr_indent = len(line) - len(line.lstrip())
            # If indent increases by more than 4 spaces without reason, flag it
            if curr_indent > prev_indent + 4 and prev_indent > 0:
                # Check if previous line ends with : (valid indent increase)
                if i > 1 and not lines[i-2].rstrip().endswith(':'):
                    logger.debug(f"Unexpected indent at line {i}")
                    return False
            prev_indent = curr_indent
        
        # Valid syntax
        try:
            import ast
            ast.parse(code)
        except SyntaxError as e:
            logger.debug(f"Syntax error: {e}")
            # If it's an indentation error, provide more context
            if 'indent' in str(e).lower():
                logger.debug("Indentation issue detected - LLM generated malformed code")
            return False
        except Exception as e:
            logger.debug(f"Parse error: {e}")
            return False
        
        return True
