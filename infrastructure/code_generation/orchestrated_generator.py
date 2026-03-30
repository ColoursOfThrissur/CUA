"""
Orchestrated Code Generator - Diff-first approach
Generates minimal changes instead of full method rewrites
"""
from typing import Dict, List, Optional, Tuple
from infrastructure.code_generation.method_extractor import MethodExtractor
from infrastructure.code_generation.code_integrator import CodeIntegrator

class OrchestratedCodeGenerator:
    def __init__(self, llm_client, analyzer):
        from shared.config.config_manager import get_config
        self.config = get_config()
        self.llm_client = llm_client
        self.analyzer = analyzer
        
        # Components
        self.extractor = MethodExtractor()
        self.integrator = CodeIntegrator()
        
        # Block-based generator
        from infrastructure.code_generation.block_generator import BlockCodeGenerator
        self.block_generator = BlockCodeGenerator(llm_client, analyzer)
    
    def generate_code(self, user_request: str, target_file: str, target_tool: Optional[str] = None, previous_errors: Optional[List[str]] = None) -> Tuple[bool, Optional[str], Optional[str]]:
        """Legacy method for backward compatibility"""
        success, code, error, _ = self.generate_code_with_plan(user_request, target_file, target_tool, previous_errors)
        return success, code, error
    
    def generate_code_with_plan(self, user_request: str, target_file: str, target_tool: Optional[str] = None, previous_errors: Optional[List[str]] = None, user_override: Optional[str] = None, base_code: Optional[str] = None) -> Tuple[bool, Optional[str], Optional[str], Optional[List[str]]]:
        """
        Generate code using intelligent strategy selection
        Returns: (success, complete_code, error_message, methods_to_modify)
        """
        
        if not target_file:
            return False, None, "No target file specified", None
        
        from infrastructure.logging.logging_system import get_logger
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
                original_code = base_code if base_code is not None else self.analyzer.get_file_content(target_file)
                return self._insert_new_method(task, target_file, method_name, original_code, previous_errors or [])
        
        # Default: method rewrite
        return self._generate_method_rewrite(task, target_file, previous_errors or [], base_code=base_code)

    def _select_strategy(self, task: str, target_file: str) -> str:
        """
        Select code generation strategy based on task intent
        Returns: 'incremental', 'insert', or 'rewrite'
        """
        task_lower = task.lower()
        
        # Refactoring: Always use rewrite (needs to modify existing + add new)
        refactoring_keywords = ['refactor', 'extract helper', 'extract method', 'extract private', 'split method']
        if any(kw in task_lower for kw in refactoring_keywords):
            return "rewrite"
        
        # Modifying existing method: use rewrite
        modify_keywords = [
            'add logging', 'add timeout', 'add validation', 'add error handling',
            'add retry', 'add caching', 'add monitoring', 'add metrics',
            'add parameter', 'add argument', 'add check', 'add support for',
            'comprehensive logging', 'logging for debugging', 'add async',
            'modify', 'update', 'change', 'improve', 'fix'
        ]
        
        for keyword in modify_keywords:
            if keyword in task_lower:
                return "rewrite"
        
        # Insert: ONLY for explicitly creating new methods
        if 'add new method' in task_lower or 'create new method' in task_lower:
            method_name = self._extract_method_name(task)
            if method_name:
                original_code = self.analyzer.get_file_content(target_file)
                if original_code:
                    methods = self.extractor.extract_methods(original_code)
                    if method_name not in methods:
                        return "insert"
        
        # Default: rewrite (safest)
        return "rewrite"
    
    def _generate_incremental_modification(self, task: str, target_file: str, previous_errors: List[str]) -> Tuple[bool, Optional[str], Optional[str], Optional[List[str]]]:
        """
        DISABLED: Block-based approach causes too many syntax errors.
        Always fallback to full method rewrite for reliability.
        """
        from infrastructure.logging.logging_system import get_logger
        logger = get_logger("code_generator")
        
        logger.info("Incremental modification disabled - using full rewrite")
        return self._generate_method_rewrite(task, target_file, previous_errors)
    
    def _generate_line_modification(self, task: str, target_file: str, method_name: str,
                                   original_code: str, previous_errors: List[str]) -> Tuple[bool, Optional[str], Optional[str]]:
        """Generate line-by-line diff modifications"""
        from infrastructure.logging.logging_system import get_logger
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
    
    def _generate_method_rewrite(self, task: str, target_file: str, previous_errors: List[str], base_code: Optional[str] = None) -> Tuple[bool, Optional[str], Optional[str], Optional[List[str]]]:
        """Generate method rewrite or insert new method"""
        from infrastructure.logging.logging_system import get_logger
        logger = get_logger("code_generator")
        
        logger.info("Using method rewrite strategy")
        
        original_code = base_code if base_code is not None else self.analyzer.get_file_content(target_file)
        methods = self.extractor.extract_methods(original_code)
        
        if not methods:
            logger.error(f"No methods found in {target_file}")
            return False, None, "No methods found in file", None
        
        # Identify target method
        method_name = self._extract_method_name(task)
        
        # CRITICAL: Fail explicitly if method name cannot be extracted
        if not method_name:
            line_hint = self._extract_target_line(task)
            if line_hint is not None:
                for name, info in methods.items():
                    start = int(info.get('start_line', -1))
                    end = int(info.get('end_line', -1))
                    if start <= line_hint <= end:
                        method_name = name
                        logger.info(f"Inferred method '{method_name}' from line hint {line_hint}")
                        break
                if not method_name and methods:
                    # Fallback: pick the nearest method start for line-hint-only tasks.
                    nearest_name = None
                    nearest_distance = None
                    for name, info in methods.items():
                        start = int(info.get('start_line', -1))
                        if start < 0:
                            continue
                        distance = abs(start - line_hint)
                        if nearest_distance is None or distance < nearest_distance:
                            nearest_distance = distance
                            nearest_name = name
                    if nearest_name:
                        method_name = nearest_name
                        logger.info(f"Inferred nearest method '{method_name}' from line hint {line_hint}")
            if not method_name:
                logger.error(f"Could not extract method name from task: {task[:100]}")
                logger.error(f"Available methods: {list(methods.keys())}")
                return False, None, "Could not infer target method from task description", None
        
        logger.info(f"Extracted method name: {method_name}")
        logger.info(f"Available methods: {list(methods.keys())}")

        explicit_targets = self._extract_explicit_method_targets(task, list(methods.keys()))
        if explicit_targets and method_name not in explicit_targets:
            logger.error(f"Method extraction mismatch. extracted={method_name}, explicit_targets={explicit_targets}")
            return False, None, f"Method extraction mismatch: expected one of {explicit_targets}, got {method_name}", None
        
        # Check if method exists
        if method_name not in methods:
            # NEW METHOD - use insert strategy
            logger.info(f"Method {method_name} doesn't exist - using insert strategy")
            return self._insert_new_method(task, target_file, method_name, original_code, previous_errors)
        
        # Method already exists - check if it needs modification
        if method_name in methods:
            # Skip "already implemented" check for refactoring tasks
            task_lower = task.lower()
            is_refactoring = any(kw in task_lower for kw in ['refactor', 'extract helper', 'extract method', 'reduce duplication'])
            
            if not is_refactoring:
                # Verify if task is actually needed (only for non-refactoring)
                method_code = methods[method_name]['code']
                if self._is_already_implemented(task, method_code):
                    logger.info(f"Method {method_name} already implements requested feature - skipping")
                    return False, None, f"Feature already implemented in {method_name}", [method_name]
        
        # EXISTING METHOD - use rewrite strategy
        method_info = methods[method_name]
        current_method = method_info['code']
        
        # Build focused context - only what LLM needs
        error_context = ""
        if previous_errors:
            error_context = "\n\nPREVIOUS ERRORS:\n" + "\n".join(f"- {e}" for e in previous_errors[-2:])
        
        # Check if refactoring task - needs special prompt
        is_refactoring_task = any(kw in task.lower() for kw in ['refactor', 'extract helper', 'extract method', 'extract private'])
        is_caching_task = 'cach' in task.lower() or 'ttl' in task.lower()
        
        if is_refactoring_task:
            prompt = self.llm_client._format_prompt(f"""Refactor this method by extracting helper.

Task: {task}

Current method:
```python
{current_method}
```
{error_context}

Rules:
1. Output BOTH the MODIFIED {method_name} method AND the NEW helper method
2. The modified {method_name} MUST call the helper method
3. Both methods with ZERO indentation
4. No class definition, no imports
5. Complete implementation, no placeholders
6. Helper method should be AFTER the main method

Example format:
```python
def main_method(self, data):
    validated = self._validate_data(data)
    return self.process(validated)

def _validate_data(self, data):
    if not data:
        raise ValueError("Empty data")
    return data.strip()
```

IMPORTANT: You MUST return BOTH methods. Do NOT return only one method.

Refactored methods:""", expect_json=False)
        elif is_caching_task:
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
            # Increase tokens significantly for refactoring (needs 2 full methods)
            if is_refactoring_task:
                max_tokens = 4096  # Large buffer for refactored method + helper
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
            
            # Skip duplicate check - we'll handle it later
            
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
                # For refactoring: this is expected, split and integrate
                if is_refactoring_task:
                    logger.info(f"Refactoring returned {len(found_methods)} methods: {found_methods} - this is correct")
                    modified_methods, new_methods = self._split_methods(code, method_name)

                    existing_method_names = set(methods.keys())
                    promoted_replacements = {
                        name: method_code
                        for name, method_code in new_methods.items()
                        if name in existing_method_names
                    }
                    truly_new_methods = {
                        name: method_code
                        for name, method_code in new_methods.items()
                        if name not in existing_method_names
                    }
                    if promoted_replacements:
                        modified_methods = {**modified_methods, **promoted_replacements}

                    result_code = self.integrator.integrate_methods(original_code, modified_methods)
                    if truly_new_methods:
                        result_code = self.integrator.add_new_methods(result_code, truly_new_methods)

                    expected_methods = list(modified_methods.keys()) + list(truly_new_methods.keys())
                    if not self.integrator.verify_expected_methods(result_code, expected_methods):
                        logger.warning(f"Attempt {attempt+1}: Integrated code missing expected methods: {expected_methods}")
                        prompt += "\n\nERROR: Integrated result missing expected methods. Keep method names stable and complete."
                        continue
                    
                    # Validate result
                    if not self._validate_syntax(result_code):
                        error_msg = self._get_syntax_error(result_code)
                        logger.warning(f"Attempt {attempt+1}: Syntax error after refactoring: {error_msg}")
                        prompt += f"\n\nERROR: {error_msg}\n\nFix the syntax."
                        continue

                    compat_ok, compat_msg = self._validate_internal_call_compatibility(result_code)
                    if not compat_ok:
                        logger.warning(f"Attempt {attempt+1}: Call compatibility error after refactoring: {compat_msg}")
                        prompt += f"\n\nERROR: {compat_msg}\n\nKeep helper signatures backward-compatible with all call sites."
                        continue
                    
                    logger.info(f"Refactoring completed successfully with {len(found_methods)} methods")
                    return True, result_code, None, [method_name]
                else:
                    # Not refactoring: reject multiple methods
                    logger.warning(f"Attempt {attempt+1}: LLM returned {len(found_methods)} methods: {found_methods}")
                    prompt += f"\n\nERROR: You returned {len(found_methods)} methods. Output ONLY 'def {method_name}', not other methods."
                    continue
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

            compat_ok, compat_msg = self._validate_internal_call_compatibility(result_code)
            if not compat_ok:
                logger.warning(f"Attempt {attempt+1}: Call compatibility error: {compat_msg}")
                prompt += f"\n\nERROR: {compat_msg}\n\nKeep helper signatures backward-compatible with all call sites."
                continue
            
            logger.info(f"Method {method_name} rewritten successfully")
            return True, result_code, None, [method_name]
        
        # Return detailed error on final failure
        last_error = f"Syntax error: {self._get_syntax_error(result_code)}" if 'result_code' in locals() else "No valid code generated"
        return False, None, last_error, [method_name]
    
    def _insert_new_method(self, task: str, target_file: str, method_name: str, original_code: str, previous_errors: List[str]) -> Tuple[bool, Optional[str], Optional[str], Optional[List[str]]]:
        """Insert new method at end of class"""
        from infrastructure.logging.logging_system import get_logger
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
        from infrastructure.logging.logging_system import get_logger
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
            from infrastructure.logging.logging_system import get_logger
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

    def _extract_explicit_method_targets(self, task: str, available_methods: Optional[List[str]] = None) -> List[str]:
        """Extract explicitly named target methods from task text."""
        import re
        targets = []
        stopwords = {
            'to', 'for', 'with', 'from', 'into', 'by', 'and', 'or',
            'the', 'a', 'an', 'in', 'on', 'of', 'at', 'as'
        }
        patterns = [
            r"\bmodify\s+([_a-zA-Z][\w_]*)\(\)",
            r"\bmodify\s+([_a-zA-Z][\w_]*)\s+method",
            r"\brefactor\s+(?:the\s+)?([_a-zA-Z][\w_]*)\s+method\b",
            r"\bupdate\s+(?:the\s+)?([_a-zA-Z][\w_]*)\s+method\b",
            r"\bchange\s+(?:the\s+)?([_a-zA-Z][\w_]*)\s+method\b",
            r"\b([_a-zA-Z][\w_]*)\(\)",
        ]
        available = set(available_methods or [])
        for pattern in patterns:
            for match in re.finditer(pattern, task, re.IGNORECASE):
                name = match.group(1)
                if not name:
                    continue
                lower_name = name.lower()
                if lower_name in stopwords:
                    continue
                if available and name not in available:
                    continue
                if name not in targets:
                    targets.append(name)
        return targets
    
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

    def _validate_internal_call_compatibility(self, code: str) -> Tuple[bool, str]:
        """Detect helper signature/call mismatches before sandbox tests."""
        try:
            import ast
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"Syntax error: line {e.lineno}: {e.msg}"
        except Exception as e:
            return False, str(e)

        class_node = next((n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)), None)
        if not class_node:
            return True, "ok"

        method_defs = {}
        for node in class_node.body:
            if isinstance(node, ast.FunctionDef):
                args = node.args.args[1:] if node.args.args else []
                total_positional = len(args)
                defaults = node.args.defaults or []
                required_positional = max(0, total_positional - len(defaults))
                method_defs[node.name] = {
                    "required_positional": required_positional,
                    "total_positional": total_positional,
                    "param_names": [a.arg for a in args],
                }

        for func in [n for n in ast.walk(class_node) if isinstance(n, ast.FunctionDef)]:
            for call in [n for n in ast.walk(func) if isinstance(n, ast.Call)]:
                if not isinstance(call.func, ast.Attribute):
                    continue
                if not isinstance(call.func.value, ast.Name) or call.func.value.id != "self":
                    continue
                target = call.func.attr
                if target not in method_defs:
                    continue
                spec = method_defs[target]

                positional_given = len(call.args)
                kw_names = {kw.arg for kw in call.keywords if kw.arg}
                for name in spec["param_names"][:spec["required_positional"]]:
                    if name in kw_names:
                        positional_given += 1

                if positional_given < spec["required_positional"]:
                    return (
                        False,
                        f"Method '{target}' requires {spec['required_positional']} args but call in '{func.name}' provides fewer"
                    )

                # Guard against refactor regressions where FAILURE path forgets error_message
                # due to positional argument misuse in result helper calls.
                target_lower = target.lower()
                if not target.startswith('_') or 'result' not in target_lower:
                    continue

                status_failure = False

                def _is_failure_node(node) -> bool:
                    if not isinstance(node, ast.Attribute):
                        return False
                    if node.attr.upper() != "FAILURE":
                        return False
                    if isinstance(node.value, ast.Name) and node.value.id.lower() in {"resultstatus"}:
                        return True
                    return isinstance(node.value, ast.Attribute) and node.value.attr.lower() == "resultstatus"

                if len(call.args) >= 2 and _is_failure_node(call.args[1]):
                    status_failure = True
                for kw in call.keywords:
                    if kw.arg == "status" and _is_failure_node(kw.value):
                        status_failure = True
                        break

                if not status_failure:
                    continue

                has_error_kw = any(kw.arg == "error_message" for kw in call.keywords if kw.arg)
                if has_error_kw:
                    continue

                error_index = -1
                if "error_message" in spec["param_names"]:
                    error_index = spec["param_names"].index("error_message")

                # If helper defines error_message but this FAILURE call doesn't pass it,
                # it's likely to regress expected failure behavior.
                if error_index >= 0:
                    if error_index >= len(call.args):
                        return (
                            False,
                            f"FAILURE call to '{target}' in '{func.name}' is missing error_message"
                        )
                    error_arg = call.args[error_index]
                    if isinstance(error_arg, ast.Constant) and isinstance(error_arg.value, str):
                        if not error_arg.value.strip():
                            return (
                                False,
                                f"FAILURE call to '{target}' in '{func.name}' has empty error_message"
                            )
                    else:
                        return (
                            False,
                            f"FAILURE call to '{target}' in '{func.name}' should pass explicit error_message"
                        )
        return True, "ok"
    
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
        
        # Prefer explicit method in Task section to avoid matching
        # helper context snippets later in the prompt.
        task_section = task
        task_match = re.search(r"Task:\s*(.+?)(?:\n\nCurrent code:|\n\ncurrent code:|\Z)", task, re.DOTALL | re.IGNORECASE)
        if task_match:
            task_section = task_match.group(1)
        
        # Blacklist common English words that aren't method names
        blacklist = {'to', 'by', 'named', 'definition', 'method', 'function', 'the', 'a', 'an', 'in', 'on', 'at', 'for', 'with', 'from'}
        
        patterns = [
            r"\bmodify\s+([_a-zA-Z][\w_]*)\(\)",  # Modify _post()
            r"\bmodify\s+([_a-zA-Z][\w_]*)\s+method",  # Modify _post method
            r"named [`'\"]([\w_]+)[`'\"]",  # named `_method_name`
            r"method [`'\"]([\w_]+)[`'\"]",  # method '_method_name'
            r"function [`'\"]([\w_]+)[`'\"]",  # function '_method_name'
            r"\bthe ([_a-zA-Z][\w_]*) method",  # the _extract method
            r"\brefactor (?:the )?([_a-zA-Z][\w_]*) method",  # refactor the _extract method
            r"\bdef ([_a-zA-Z][\w_]*)",  # def _method_name
            r"\bcreate ([_a-zA-Z][\w_]*) method",  # create _method_name method
            r"\badd ([_a-zA-Z][\w_]*) method",  # add _method_name method
            r"([_a-zA-Z][\w_]*)\(\)",  # _method_name()
        ]
        
        for pattern in patterns:
            match = re.search(pattern, task_section, re.IGNORECASE)
            if match:
                name = match.group(1)
                # Validate: must start with letter/underscore, not in blacklist
                if name and name.lower() not in blacklist and re.match(r'^[_a-zA-Z][\w_]*$', name):
                    return name
        
        # Fallback to full prompt scan if task section had no match
        for pattern in patterns:
            match = re.search(pattern, task, re.IGNORECASE)
            if match:
                name = match.group(1)
                if name and name.lower() not in blacklist and re.match(r'^[_a-zA-Z][\w_]*$', name):
                    return name
        
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

    def _extract_target_line(self, task: str) -> Optional[int]:
        """Extract target line number from task strings like 'line 35'."""
        import re
        match = re.search(r"\bline\s+(\d+)\b", task, re.IGNORECASE)
        if not match:
            return None
        try:
            return int(match.group(1))
        except ValueError:
            return None
    
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
        from infrastructure.logging.logging_system import get_logger
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
