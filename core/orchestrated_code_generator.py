"""
Orchestrated Code Generator - Diff-first approach
Generates minimal changes instead of full method rewrites
"""
from typing import Dict, List, Optional, Tuple
from core.method_extractor import MethodExtractor
from core.code_integrator import CodeIntegrator

class OrchestratedCodeGenerator:
    def __init__(self, llm_client, analyzer):
        from core.config_manager import get_config
        self.config = get_config()
        self.llm_client = llm_client
        self.analyzer = analyzer
        
        # Components
        self.extractor = MethodExtractor()
        self.integrator = CodeIntegrator()
        
        # Block-based generator
        from core.block_code_generator import BlockCodeGenerator
        self.block_generator = BlockCodeGenerator(llm_client, analyzer)
    
    def generate_code(self, user_request: str, target_file: str, target_tool: Optional[str] = None, previous_errors: Optional[List[str]] = None) -> Tuple[bool, Optional[str], Optional[str]]:
        """Legacy method for backward compatibility"""
        success, code, error, _ = self.generate_code_with_plan(user_request, target_file, target_tool, previous_errors)
        return success, code, error
    
    def generate_code_with_plan(self, user_request: str, target_file: str, target_tool: Optional[str] = None, previous_errors: Optional[List[str]] = None, user_override: Optional[str] = None) -> Tuple[bool, Optional[str], Optional[str], Optional[List[str]]]:
        """
        Generate code using intelligent strategy selection
        Returns: (success, complete_code, error_message, methods_to_modify)
        """
        
        if not target_file:
            return False, None, "No target file specified", None
        
        from core.logging_system import get_logger
        logger = get_logger("code_generator")
        
        logger.info(f"=== CODE GENERATION START ===")
        logger.info(f"Target file: {target_file}")
        logger.info(f"Request: {user_request[:100]}")
        if user_override:
            logger.info(f"USER REQUEST MODE: {user_override[:80]}")
        
        task = user_override or user_request
        
        # Intelligent strategy selection
        strategy = self._select_strategy(task, target_file)
        logger.info(f"Selected strategy: {strategy}")
        
        if strategy == "incremental":
            return self._generate_incremental_modification(task, target_file, previous_errors or [])
        elif strategy == "insert":
            method_name = self._extract_method_name(task)
            if method_name:
                original_code = self.analyzer.get_file_content(target_file)
                return self._insert_new_method(task, target_file, method_name, original_code, previous_errors or [])
        
        # Default: method rewrite
        return self._generate_method_rewrite(task, target_file, previous_errors or [])

    def _select_strategy(self, task: str, target_file: str) -> str:
        """
        Select code generation strategy based on task intent
        Returns: 'incremental', 'insert', or 'rewrite'
        """
        task_lower = task.lower()
        
        # Incremental: Adding features to existing methods without full rewrite
        incremental_keywords = [
            'add logging', 'add timeout', 'add validation', 'add error handling',
            'add retry', 'add caching', 'add monitoring', 'add metrics',
            'add parameter', 'add argument', 'add check', 'add support for',
            'comprehensive logging', 'logging for debugging', 'add async'
        ]
        
        for keyword in incremental_keywords:
            if keyword in task_lower:
                return "rewrite"  # Changed: use rewrite for reliability
        
        # Insert: Creating new methods
        if 'add new method' in task_lower or 'create method' in task_lower:
            return "insert"
        
        # Check if method doesn't exist (insert)
        method_name = self._extract_method_name(task)
        if method_name:
            original_code = self.analyzer.get_file_content(target_file)
            if original_code:
                methods = self.extractor.extract_methods(original_code)
                if method_name not in methods:
                    return "insert"
        
        # Default: rewrite for fixes, refactors, major changes
        return "rewrite"
    
    def _generate_incremental_modification(self, task: str, target_file: str, previous_errors: List[str]) -> Tuple[bool, Optional[str], Optional[str], Optional[List[str]]]:
        """
        Generate incremental modifications using block-based approach with fallbacks
        Strategy: Block → Line → Full method rewrite
        """
        from core.logging_system import get_logger
        logger = get_logger("code_generator")
        
        logger.info("Using incremental modification strategy")
        
        original_code = self.analyzer.get_file_content(target_file)
        methods = self.extractor.extract_methods(original_code)
        
        if not methods:
            logger.error(f"No methods found in {target_file}")
            return False, None, "No methods found in file", None
        
        # Identify target method
        method_name = self._extract_method_name(task)
        if not method_name or method_name not in methods:
            # Try to find method mentioned in task
            for m in methods.keys():
                if m in task or m.lstrip('_') in task:
                    method_name = m
                    break
            # If still not found, use smart selection based on task type
            if not method_name or method_name not in methods:
                # For caching/performance features, target execution method
                if any(keyword in task.lower() for keyword in ['caching', 'cache', 'performance', 'timeout', 'retry']):
                    for preferred in ['_execute', 'execute', '_handle', 'run', '_get', '_post']:
                        if preferred in methods:
                            method_name = preferred
                            break
                # For other features, prefer execution methods over __init__
                if not method_name:
                    for preferred in ['_execute', 'execute', '_handle', 'run', '_get', '_post']:
                        if preferred in methods:
                            method_name = preferred
                            break
                # Last resort: first non-init method
                if not method_name:
                    non_init = [m for m in methods.keys() if m != '__init__']
                    method_name = non_init[0] if non_init else list(methods.keys())[0]
        
        logger.info(f"Target method: {method_name}")
        
        # STRATEGY 1: Block-based modification (preferred)
        logger.info("Trying block-based modification")
        success, code, error = self.block_generator.generate_block_modification(
            task, target_file, method_name, original_code, previous_errors
        )
        
        if success and code:
            # Validate block result
            if self._validate_syntax(code):
                logger.info("Block-based modification succeeded")
                return True, code, None, [method_name]
            else:
                logger.warning(f"Block produced invalid code: {self._get_syntax_error(code)}")
        else:
            logger.warning(f"Block-based failed: {error}")
        
        # STRATEGY 2: Line-based modification (fallback)
        logger.info("Trying line-based modification")
        success, code, error = self._generate_line_modification(
            task, target_file, method_name, original_code, previous_errors
        )
        
        if success:
            logger.info("Line-based modification succeeded")
            return True, code, None, [method_name]
        
        logger.warning(f"Line-based failed: {error}")
        
        # STRATEGY 3: Full method rewrite (last resort)
        logger.info("Falling back to full method rewrite")
        return self._generate_method_rewrite(task, target_file, previous_errors)
    
    def _generate_line_modification(self, task: str, target_file: str, method_name: str,
                                   original_code: str, previous_errors: List[str]) -> Tuple[bool, Optional[str], Optional[str]]:
        """Generate line-by-line diff modifications"""
        from core.logging_system import get_logger
        logger = get_logger("line_generator")
        
        method_code = self.extractor.extract_methods(original_code).get(method_name, {}).get('code')
        if not method_code:
            return False, None, f"Method {method_name} not found"
        
        error_context = ""
        if previous_errors:
            error_context = "\n\nPREVIOUS ERRORS:\n" + "\n".join(f"- {e}" for e in previous_errors[-2:])
        
        prompt = self.llm_client._format_prompt(f"""Generate line modifications.

Task: {task}

Method:
```python
{method_code}
```
{error_context}

Format:
+5: new line
~10: modified line

Modifications:""", expect_json=False)
        
        for attempt in range(2):
            response = self.llm_client._call_llm(prompt, temperature=0.1, max_tokens=1024, expect_json=False)
            if not response:
                prompt += "\n\nERROR: No response."
                continue
            
            modifications = self._parse_line_diffs(response)
            if not modifications:
                prompt += "\n\nERROR: Use +N: or ~N: format."
                continue
            
            modified_method = self._apply_line_diffs(method_code, modifications)
            if not modified_method:
                prompt += "\n\nERROR: Invalid line numbers."
                continue
            
            modified_file = self.integrator.integrate_methods(original_code, {method_name: modified_method})
            
            if not self._validate_syntax(modified_file):
                error_msg = self._get_syntax_error(modified_file)
                prompt += f"\n\nERROR: {error_msg}"
                continue
            
            return True, modified_file, None
        
        return False, None, "Line modification failed"
    
    def _parse_line_diffs(self, response: str) -> List[dict]:
        """Parse line diff format"""
        import re
        modifications = []
        for line in response.split('\n'):
            match = re.match(r'^([+~])(\d+):\s*(.+)$', line.strip())
            if match:
                op, line_num, code = match.groups()
                modifications.append({
                    'op': 'insert' if op == '+' else 'modify',
                    'line': int(line_num),
                    'code': code
                })
        return modifications
    
    def _apply_line_diffs(self, method_code: str, modifications: List[dict]) -> Optional[str]:
        """Apply line modifications"""
        lines = method_code.split('\n')
        modifications.sort(key=lambda x: x['line'], reverse=True)
        
        for mod in modifications:
            line_num = mod['line'] - 1
            if mod['op'] == 'insert':
                if 0 <= line_num <= len(lines):
                    lines.insert(line_num, mod['code'])
            elif mod['op'] == 'modify':
                if 0 <= line_num < len(lines):
                    lines[line_num] = mod['code']
        
        return '\n'.join(lines)
    
    def _generate_method_rewrite(self, task: str, target_file: str, previous_errors: List[str]) -> Tuple[bool, Optional[str], Optional[str], Optional[List[str]]]:
        """Generate method rewrite or insert new method"""
        from core.logging_system import get_logger
        logger = get_logger("code_generator")
        
        logger.info("Using method rewrite strategy")
        
        original_code = self.analyzer.get_file_content(target_file)
        methods = self.extractor.extract_methods(original_code)
        
        if not methods:
            logger.error(f"No methods found in {target_file}")
            return False, None, "No methods found in file", None
        
        # Identify target method
        method_name = self._extract_method_name(task)
        
        # Check if method exists
        if method_name and method_name not in methods:
            # NEW METHOD - use insert strategy
            logger.info(f"Method {method_name} doesn't exist - using insert strategy")
            return self._insert_new_method(task, target_file, method_name, original_code, previous_errors)
        
        # Method already exists - check if it needs modification
        if method_name and method_name in methods:
            # Verify if task is actually needed
            method_code = methods[method_name]['code']
            if self._is_already_implemented(task, method_code):
                logger.info(f"Method {method_name} already implements requested feature - skipping")
                return False, None, f"Feature already implemented in {method_name}", [method_name]
        
        # EXISTING METHOD - use rewrite strategy
        if not method_name or method_name not in methods:
            method_name = list(methods.keys())[0]
        
        method_info = methods[method_name]
        current_method = method_info['code']
        
        # Build focused context - only what LLM needs
        error_context = ""
        if previous_errors:
            error_context = "\n\nPREVIOUS ERRORS:\n" + "\n".join(f"- {e}" for e in previous_errors[-2:])
        
        # Check if caching task - needs special prompt
        is_caching_task = any(kw in task.lower() for kw in ['add caching', 'add cache', 'caching mechanism'])
        
        if is_caching_task:
            prompt = self.llm_client._format_prompt(f"""Add caching to this method.

Task: {task}

Current method:
```python
{current_method}
```
{error_context}

Rules:
1. Output ONLY ONE method: 'def {method_name}'
2. Add caching INLINE using a dict (e.g., self._cache = {{}})
3. Do NOT create separate cache helper methods
4. Check cache at start, store result before return
5. Return method with ZERO indentation (no leading spaces)
6. Output raw Python only

Example (NO leading spaces):
```python
def analyze(self, file):
    # Check cache
    if hasattr(self, '_cache') and file in self._cache:
        return self._cache[file]
    # Original logic
    result = self.process(file)
    # Store in cache
    if not hasattr(self, '_cache'):
        self._cache = {{}}
    self._cache[file] = result
    return result
```

Modified method:""", expect_json=False)
        else:
            # Give LLM ONLY the method to modify, not entire file
            prompt = self.llm_client._format_prompt(f"""Modify this method to complete the task.

Task: {task}

Current method:
```python
{current_method}
```
{error_context}

Rules:
1. Output COMPLETE method starting with 'def {method_name}'
2. Include ALL original code plus your modifications
3. Do NOT add class definition - only the method
4. Do NOT add import statements inside the method - imports go at module level
5. No placeholders, TODO, or comments like "# existing code"
6. Return method with ZERO indentation (no leading spaces)
7. Output raw Python only - no JSON, no explanations
8. Code MUST be different from current method

Good example (NO leading spaces):
```python
def execute(self, param):
    logger = logging.getLogger(__name__)
    logger.debug(f"Starting with {{param}}")
    result = self.process(param)
    return result
```

Modified method:""", expect_json=False)
        
        for attempt in range(2):
            # Increase temperature on retry to get different output
            temp = 0.2 if attempt == 0 else 0.4
            # Increase tokens for multi-method tasks
            method_count = len(task.split('method')) - 1
            if method_count > 1 or 'add' in task.lower() and 'method' in task.lower():
                max_tokens = 3072  # Large buffer for multiple methods
            else:
                max_tokens = 1536
            
            response = self.llm_client._call_llm(prompt, temperature=temp, max_tokens=max_tokens, expect_json=False)
            if not response:
                logger.warning(f"Attempt {attempt+1}: No response")
                prompt += "\n\nERROR: No response. Generate complete method."
                continue
            
            code = self._extract_code(response)
            if not code:
                logger.warning(f"Attempt {attempt+1}: Could not extract code")
                prompt += "\n\nERROR: Use ```python blocks."
                continue
            
            # CRITICAL: Check if LLM returned nested methods (common Qwen error)
            import re
            found_methods = re.findall(r'^\s*def (\w+)\(', code, re.MULTILINE)
            if len(found_methods) > 1:
                logger.warning(f"Attempt {attempt+1}: LLM returned {len(found_methods)} methods: {found_methods}")
                prompt += f"\n\nERROR: You returned {len(found_methods)} methods. Output ONLY 'def {method_name}', not other methods."
                continue
            
            # CRITICAL: Check if LLM added class definition
            if 'class ' in code and f'def {method_name}' in code:
                # Extract just the method, remove class wrapper
                import re
                method_match = re.search(rf'(    def {method_name}\(.+?\n(?:(?:    .+\n)|(?:\n))*)', code, re.DOTALL)
                if method_match:
                    code = method_match.group(1)
                    logger.info(f"Removed class wrapper, extracted method only")
                else:
                    logger.warning(f"Attempt {attempt+1}: LLM added class definition")
                    prompt += f"\n\nERROR: Do NOT add 'class' definition. Output ONLY the method 'def {method_name}'."
                    continue
            
            # CRITICAL: Check if code actually changed
            if code.strip() == current_method.strip():
                logger.warning(f"Attempt {attempt+1}: Code unchanged")
                prompt += f"\n\nERROR: You returned the EXACT SAME code. You MUST make changes for: {task}"
                continue
            
            # CRITICAL: Check if super().__init__() was removed from __init__
            if method_name == '__init__':
                if 'super().__init__()' in current_method and 'super().__init__()' not in code:
                    logger.warning(f"Attempt {attempt+1}: Removed super().__init__() call")
                    prompt += "\n\nERROR: You removed 'super().__init__()'. This is required - keep it."
                    continue
            
            if f'def {method_name}' not in code:
                logger.warning(f"Attempt {attempt+1}: Wrong method signature")
                prompt += f"\n\nERROR: Must contain 'def {method_name}'."
                continue
            
            # Check if LLM returned multiple methods
            import re
            found_methods = re.findall(r'^\s*def (\w+)\(', code, re.MULTILINE)
            
            if len(found_methods) > 1:
                # Split and handle multiple methods
                modified_methods, new_methods = self._split_methods(code, method_name)
                result_code = self.integrator.integrate_methods(original_code, modified_methods)
                if new_methods:
                    result_code = self.integrator.add_new_methods(result_code, new_methods)
            else:
                # Single method - direct replacement
                result_code = self.integrator.integrate_methods(original_code, {method_name: code})
            
            # Validate result
            if not self._validate_syntax(result_code):
                error_msg = self._get_syntax_error(result_code)
                logger.warning(f"Attempt {attempt+1}: Syntax error: {error_msg}")
                # Show LLM the ACTUAL error with line numbers
                lines = result_code.split('\n')
                numbered = '\n'.join([f"{i+1:3d}: {line}" for i, line in enumerate(lines[:50])])
                prompt += f"\n\nERROR: {error_msg}\n\nYour code (first 50 lines):\n{numbered}\n\nFix the indentation/syntax."
                continue
            
            logger.info(f"Method {method_name} rewritten successfully")
            return True, result_code, None, [method_name]
        
        # Return detailed error on final failure
        last_error = f"Syntax error: {self._get_syntax_error(result_code)}" if 'result_code' in locals() else "No valid code generated"
        return False, None, last_error, [method_name]
    
    def _insert_new_method(self, task: str, target_file: str, method_name: str, original_code: str, previous_errors: List[str]) -> Tuple[bool, Optional[str], Optional[str], Optional[List[str]]]:
        """Insert new method at end of class"""
        from core.logging_system import get_logger
        logger = get_logger("code_generator")
        
        logger.info(f"Inserting new method: {method_name}")
        
        error_context = ""
        if previous_errors:
            error_context = "\n\nPREVIOUS ERRORS:\n" + "\n".join(f"- {e}" for e in previous_errors[-2:])
        
        prompt = self.llm_client._format_prompt(f"""Create a new method for this class.

Task: {task}
Method name: {method_name}
{error_context}

Rules:
1. Output ONLY the new method (def {method_name}...)
2. Include complete implementation
3. No placeholders or TODO
4. Use 4-space indentation
5. Output raw Python only

New method:""", expect_json=False)
        
        for attempt in range(2):
            response = self.llm_client._call_llm(prompt, temperature=0.2, max_tokens=2048, expect_json=False)
            if not response:
                logger.warning(f"Attempt {attempt+1}: No response")
                prompt += "\n\nERROR: No response. Generate complete method."
                continue
            
            code = self._extract_code(response)
            if not code:
                logger.warning(f"Attempt {attempt+1}: Could not extract code")
                prompt += "\n\nERROR: Use ```python blocks."
                continue
            
            if f'def {method_name}' not in code:
                logger.warning(f"Attempt {attempt+1}: Wrong method name")
                prompt += f"\n\nERROR: Must contain 'def {method_name}'."
                continue
            
            # Insert at end of class
            result_code = self.integrator.add_new_methods(original_code, {method_name: code})
            
            if not self._validate_syntax(result_code):
                error_msg = self._get_syntax_error(result_code)
                logger.warning(f"Attempt {attempt+1}: Syntax error: {error_msg}")
                prompt += f"\n\nERROR: {error_msg}"
                continue
            
            logger.info(f"Method {method_name} inserted successfully")
            return True, result_code, None, [method_name]
        
        return False, None, "Method insert failed after 2 attempts", [method_name]
    
    def _split_methods(self, code: str, primary_method: str) -> Tuple[Dict[str, str], Dict[str, str]]:
        """Split LLM response into modified and new methods"""
        import re
        modified = {}
        new = {}
        
        method_blocks = re.split(r'(^\s*def \w+\()', code, flags=re.MULTILINE)
        current_method = None
        current_code = []
        
        for block in method_blocks:
            if re.match(r'^\s*def (\w+)\(', block):
                # Save previous
                if current_method and current_code:
                    full = ''.join(current_code)
                    if current_method == primary_method:
                        modified[current_method] = full
                    else:
                        new[current_method] = full
                # Start new
                match = re.match(r'^\s*def (\w+)\(', block)
                current_method = match.group(1)
                current_code = [block]
            elif current_method:
                current_code.append(block)
        
        # Save last
        if current_method and current_code:
            full = ''.join(current_code)
            if current_method == primary_method:
                modified[current_method] = full
            else:
                new[current_method] = full
        
        return modified, new
    
    def _generate_incremental(self, task: str, target_file: str, target_tool: Optional[str], previous_errors: List[str]) -> Tuple[bool, Optional[str], Optional[str], Optional[List[str]]]:
        """Generate new file"""
        from core.logging_system import get_logger
        logger = get_logger("code_generator")
        
        # For test files
        if 'test_' in target_file:
            return self._generate_test_file(target_file, task, target_tool, previous_errors)
        
        # For other new files
        logger.info("Generating new file")
        
        error_context = ""
        if previous_errors:
            error_context = "\n\nPREVIOUS ERRORS:\n" + "\n".join(f"- {e}" for e in previous_errors[-2:])
        
        prompt = self.llm_client._format_prompt(f"""Create a new Python file.

Task: {task}
File: {target_file}
{error_context}

Include:
1. All necessary imports
2. Complete class definition
3. All required methods
4. No placeholders or TODO comments

Complete file:""", expect_json=False)
        
        response = self.llm_client._call_llm(prompt, temperature=0.3, max_tokens=2048, expect_json=False)
        if not response:
            return False, None, "No response from LLM", None
        
        code = self._extract_code(response)
        if code and self._validate_syntax(code):
            logger.info("New file generated")
            return True, code, None, []
        
        return False, None, "Failed to generate new file", None
    
    def _generate_test_file(self, target_file: str, task: str, target_tool: Optional[str], previous_errors: List[str]) -> Tuple[bool, Optional[str], Optional[str], Optional[List[str]]]:
        """Generate test file with anti-pattern prevention"""
        
        if not target_tool:
            tool_name = target_file.replace('tests/unit/test_', '').replace('.py', '')
            target_tool = f"tools/{tool_name}.py"
        
        tool_code = self.analyzer.get_file_content(target_tool)
        if not tool_code:
            return False, None, f"Tool file not found: {target_tool}", None
        
        # Extract class name
        import re
        class_match = re.search(r'class (\w+)', tool_code)
        class_name = class_match.group(1) if class_match else "Tool"
        tool_name = target_tool.replace('tools/', '').replace('.py', '')
        
        error_context = ""
        if previous_errors:
            error_context = "\n\nPREVIOUS ERRORS:\n" + "\n".join(f"- {e}" for e in previous_errors[-2:])
        
        prompt = self.llm_client._format_prompt(f"""Create a pytest test file.

Task: {task}
Test file: {target_file}
Tool: {tool_name}.{class_name}

Tool code preview:
```python
{tool_code[:1000]}
```
{error_context}

CRITICAL - Correct pattern:
```python
# CORRECT
tool = {class_name}()
result = tool.execute("operation", {{"param": "value"}})
assert result.status == ResultStatus.SUCCESS

# WRONG - result.execute() does NOT exist
```

Required imports:
- from tools.{tool_name} import {class_name}
- from tools.tool_result import ToolResult, ResultStatus

Rules:
1. Use pytest style (def test_name)
2. Call tool.execute(), NOT result.execute()
3. Test multiple operations
4. Include assertions

Complete test file:""", expect_json=False)
        
        response = self.llm_client._call_llm(prompt, temperature=0.2, max_tokens=1536, expect_json=False)
        if not response:
            return False, None, "No response from LLM", None
        
        code = self._extract_code(response)
        
        # Auto-fix common mistake
        if code and 'result.execute(' in code:
            from core.logging_system import get_logger
            logger = get_logger("code_generator")
            logger.info("Auto-fixing result.execute() → tool.execute()")
            code = code.replace('result.execute(', 'tool.execute(')
        
        if code and 'def test_' in code and self._validate_syntax(code):
            return True, code, None, []
        
        return False, None, "Failed to generate test file", None
    
    def _extract_code(self, response: str) -> Optional[str]:
        """Extract code from response"""
        import json
        
        # Check for JSON (Qwen issue)
        if response.strip().startswith('{'):
            try:
                data = json.loads(response)
                # Try multiple keys that Qwen might use
                for key in ['code', 'method_code', 'modified_method', 'result', 'fixed_code', 'output']:
                    if key in data and isinstance(data[key], str):
                        # Unescape newlines if JSON-escaped
                        code = data[key]
                        if '\\n' in code:
                            code = code.replace('\\n', '\n')
                        return code
            except:
                pass
        
        # Extract from markdown
        if '```python' in response:
            start = response.find('```python') + 9
            end = response.find('```', start)
            if end != -1:
                return response[start:end].strip()
        
        if '```' in response:
            start = response.find('```') + 3
            newline = response.find('\n', start)
            if newline != -1:
                start = newline + 1
            end = response.find('```', start)
            if end != -1:
                return response[start:end].strip()
        
        return None
    
    def _validate_method(self, code: str, method_name: str) -> bool:
        """Validate method"""
        if f'def {method_name}' not in code:
            return False
        if method_name != '__init__' and 'return' not in code:
            return False
        return self._validate_syntax(code)
    
    def _validate_syntax(self, code: str) -> bool:
        """Validate Python syntax"""
        try:
            import ast
            ast.parse(code)
            return True
        except:
            return False
    
    def _infer_task_type(self, task: str) -> str:
        """Infer task type from description"""
        task_lower = task.lower()
        if 'fix' in task_lower or 'bug' in task_lower:
            return 'fix_bug'
        elif 'add' in task_lower or 'validation' in task_lower:
            return 'add_validation'
        else:
            return 'improve_code'
    
    def _extract_method_name(self, task: str) -> Optional[str]:
        """Extract method name from task"""
        import re
        patterns = [r'method (\w+)', r'function (\w+)', r'def (\w+)', r'(\w+)\(\)']
        for pattern in patterns:
            match = re.search(pattern, task)
            if match:
                return match.group(1)
        return None
    
    def _get_syntax_error(self, code: str) -> str:
        """Get detailed syntax error message"""
        try:
            import ast
            ast.parse(code)
            return "No error"
        except SyntaxError as e:
            return f"Line {e.lineno}: {e.msg}"
        except Exception as e:
            return str(e)
    
    def _is_already_implemented(self, task: str, method_code: str) -> bool:
        """Check if task is already implemented in method"""
        task_lower = task.lower()
        code_lower = method_code.lower()
        
        # Check for common patterns
        if 'add _put' in task_lower and 'def _put' in code_lower:
            return True
        if 'add _delete' in task_lower and 'def _delete' in code_lower:
            return True
        if 'url validation' in task_lower and '_is_allowed_url' in code_lower:
            return True
        if 'error handling' in task_lower and 'try:' in code_lower and 'except' in code_lower:
            return True
        
        return False
    
    def _fix_syntax_error(self, full_code: str, inserted_block: str, error: str, task: str) -> Optional[str]:
        """Ask LLM to fix syntax error"""
        from core.logging_system import get_logger
        logger = get_logger("code_generator")
        
        logger.info("Asking LLM to fix syntax error", error=error)
        
        prompt = self.llm_client._format_prompt(f"""Fix this syntax error.

Task: {task}
Error: {error}

Inserted block:
```python
{inserted_block}
```

Full file with error:
```python
{full_code[:2000]}
```

Output the COMPLETE corrected file:""", expect_json=False)
        
        response = self.llm_client._call_llm(prompt, temperature=0.1, max_tokens=2048, expect_json=False)
        if not response:
            return None
        
        fixed = self._extract_code(response)
        return fixed if fixed else None
