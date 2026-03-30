"""
Block-based Code Generator - Modify specific code blocks instead of entire methods
"""
from typing import Optional, Tuple, List
import re

class BlockCodeGenerator:
    def __init__(self, llm_client, analyzer):
        self.llm_client = llm_client
        self.analyzer = analyzer
    
    def generate_block_modification(self, task: str, target_file: str, method_name: str, 
                                   original_code: str, previous_errors: List[str] = None) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Generate code by modifying specific blocks within a method
        Returns: (success, modified_code, error_message)
        """
        from infrastructure.logging.logging_system import get_logger
        logger = get_logger("block_generator")
        
        logger.info(f"Block modification for {method_name} in {target_file}")
        
        # Extract the target method
        method_code = self._extract_method(original_code, method_name)
        if not method_code:
            return False, None, f"Method {method_name} not found"
        
        # Identify target block within method
        block_location = self._identify_target_block(task, method_code)
        
        error_context = ""
        if previous_errors:
            error_context = "\n\nPREVIOUS ERRORS:\n" + "\n".join(f"- {e}" for e in previous_errors[-2:])
        
        # Ask LLM to generate ONLY the modification block
        prompt = self.llm_client._format_prompt(f"""Generate ONLY the code block to add/modify for this task.

Task: {task}
Method: {method_name}
Location: {block_location}

Current method:
```python
{method_code}
```
{error_context}

Rules:
1. Output ONLY the new/modified code block (20-100 lines max)
2. Do NOT output the entire method - ONLY the new block
3. Use proper indentation (4 spaces per level)
4. No placeholders, TODO, or comments like "# existing code"
5. Output raw Python only - no explanations
6. CRITICAL: The code MUST be different from the current method
7. CRITICAL: Match indentation exactly (4 spaces = 1 level)

Example of what to output:
```python
import logging
logger = logging.getLogger(__name__)
logger.debug(f"Starting {{method_name}}")
```

Code block to add/modify:""", expect_json=False)
        
        for attempt in range(2):
            response = self.llm_client._call_llm(prompt, temperature=0.1, max_tokens=1024, expect_json=False)
            if not response:
                logger.warning(f"Attempt {attempt+1}: No response")
                prompt += "\n\nERROR: No response. Generate code block."
                continue
            
            block_code = self._extract_code(response)
            if not block_code:
                logger.warning(f"Attempt {attempt+1}: Could not extract code")
                prompt += "\n\nERROR: Use ```python blocks."
                continue
            
            # Extract imports from block
            imports, block_without_imports = self._extract_imports(block_code)
            
            # Insert block into method
            modified_method = self._insert_block(method_code, block_without_imports, block_location, task)
            if not modified_method:
                logger.warning(f"Attempt {attempt+1}: Failed to insert block")
                prompt += "\n\nERROR: Block insertion failed. Check indentation."
                continue
            
            # Replace method in original file
            modified_file = self._replace_method(original_code, method_name, modified_method)
            
            # Add imports at file level
            if imports:
                modified_file = self._add_imports_to_file(modified_file, imports)
            
            # Validate syntax
            if not self._validate_syntax(modified_file):
                error_msg = self._get_syntax_error(modified_file)
                logger.warning(f"Attempt {attempt+1}: Syntax error: {error_msg}")
                prompt += f"\n\nERROR: {error_msg}"
                continue
            
            logger.info(f"Block modification successful")
            return True, modified_file, None
        
        return False, None, "Block modification failed after 2 attempts"
    
    def _identify_target_block(self, task: str, method_code: str) -> str:
        """Identify where in the method to add/modify code"""
        task_lower = task.lower()
        
        # Logging: after method start, before main logic
        if 'logging' in task_lower or 'log' in task_lower:
            if 'def ' in method_code:
                return "after_method_signature"
        
        # Validation: at method start
        if 'validation' in task_lower or 'validate' in task_lower or 'check' in task_lower:
            return "after_method_signature"
        
        # Timeout: in function call
        if 'timeout' in task_lower:
            return "in_function_call"
        
        # Error handling: wrap existing code
        if 'error' in task_lower or 'exception' in task_lower:
            return "wrap_try_except"
        
        # Retry: wrap existing code
        if 'retry' in task_lower:
            return "wrap_retry_loop"
        
        # Default: after method signature
        return "after_method_signature"
    
    def _insert_block(self, method_code: str, block_code: str, location: str, task: str) -> Optional[str]:
        """Insert code block at specified location"""
        lines = method_code.split('\n')
        
        if location == "after_method_signature":
            # Insert after def line
            for i, line in enumerate(lines):
                if line.strip().startswith('def '):
                    # Find end of signature
                    sig_end = i
                    for j in range(i, len(lines)):
                        if ':' in lines[j]:
                            sig_end = j
                            break
                    
                    # Get indentation from first line of method body
                    body_indent = ""
                    if sig_end + 1 < len(lines):
                        body_line = lines[sig_end + 1]
                        body_indent = body_line[:len(body_line) - len(body_line.lstrip())]
                    else:
                        # Default: method indent + 4 spaces
                        method_indent = line[:len(line) - len(line.lstrip())]
                        body_indent = method_indent + "    "
                    
                    # Process block lines with proper indentation
                    block_lines = []
                    block_raw_lines = block_code.split('\n')
                    
                    # Find minimum indentation in block (excluding empty lines)
                    min_indent = float('inf')
                    for block_line in block_raw_lines:
                        if block_line.strip():  # Non-empty
                            current_indent = len(block_line) - len(block_line.lstrip())
                            min_indent = min(min_indent, current_indent)
                    
                    if min_indent == float('inf'):
                        min_indent = 0
                    
                    # Re-indent all lines relative to minimum
                    for block_line in block_raw_lines:
                        if block_line.strip():  # Non-empty line
                            # Remove minimum indentation
                            relative_indent = len(block_line) - len(block_line.lstrip()) - min_indent
                            stripped = block_line.lstrip()
                            # Add body indent + relative indent
                            new_line = body_indent + (" " * relative_indent) + stripped
                            block_lines.append(new_line)
                        else:
                            block_lines.append('')  # Keep empty lines
                    
                    # Insert after signature
                    lines = lines[:sig_end + 1] + [''] + block_lines + [''] + lines[sig_end + 1:]
                    return '\n'.join(lines)
        
        elif location == "in_function_call":
            # Add parameter to function calls
            modified = method_code
            # Find function calls and add timeout parameter
            if 'timeout' in task.lower():
                # Simple approach: add timeout=X to function calls
                modified = re.sub(r'(\w+\([^)]*)\)', r'\1, timeout=10)', modified)
            return modified
        
        elif location == "wrap_try_except":
            # Wrap main logic in try-except
            # Find first non-docstring, non-validation code
            start_idx = 0
            for i, line in enumerate(lines):
                if line.strip().startswith('def '):
                    start_idx = i + 1
                    break
            
            # Skip docstring and validation
            while start_idx < len(lines) and (lines[start_idx].strip().startswith('"""') or 
                                              lines[start_idx].strip().startswith('if not') or
                                              not lines[start_idx].strip()):
                start_idx += 1
            
            indent = self._get_indent(lines[start_idx]) if start_idx < len(lines) else "        "
            
            # Wrap remaining code
            wrapped = lines[:start_idx] + [f"{indent}try:"]
            for line in lines[start_idx:]:
                wrapped.append("    " + line if line.strip() else line)
            
            # Add except block
            wrapped.extend([
                f"{indent}except Exception as e:",
                f"{indent}    {block_code.strip()}"
            ])
            
            return '\n'.join(wrapped)
        
        # Default: append at end
        return method_code + '\n\n' + block_code
    
    def _extract_method(self, code: str, method_name: str) -> Optional[str]:
        """Extract method code from file"""
        from infrastructure.code_generation.method_extractor import MethodExtractor
        extractor = MethodExtractor()
        methods = extractor.extract_methods(code)
        return methods.get(method_name, {}).get('code')
    
    def _replace_method(self, original_code: str, method_name: str, new_method: str) -> str:
        """Replace method in original code"""
        from infrastructure.code_generation.code_integrator import CodeIntegrator
        integrator = CodeIntegrator()
        return integrator.integrate_methods(original_code, {method_name: new_method})
    
    def _get_indent(self, line: str) -> str:
        """Get indentation of a line"""
        return line[:len(line) - len(line.lstrip())]
    
    def _extract_code(self, response: str) -> Optional[str]:
        """Extract code from response"""
        if '```python' in response:
            start = response.find('```python') + 9
            end = response.find('```', start)
            if end != -1:
                return response[start:end].strip()
        
        if '```' in response:
            start = response.find('```') + 3
            end = response.find('```', start)
            if end != -1:
                return response[start:end].strip()
        
        return response.strip()
    
    def _validate_syntax(self, code: str) -> bool:
        """Validate Python syntax"""
        try:
            import ast
            ast.parse(code)
            return True
        except:
            return False
    
    def _get_syntax_error(self, code: str) -> str:
        """Get syntax error message"""
        try:
            import ast
            ast.parse(code)
            return "No error"
        except SyntaxError as e:
            return f"Line {e.lineno}: {e.msg}"
        except Exception as e:
            return str(e)

    
    def _extract_imports(self, code: str) -> Tuple[List[str], str]:
        """Extract import statements from code block"""
        import re
        imports = []
        non_import_lines = []
        
        for line in code.split('\n'):
            stripped = line.strip()
            if stripped.startswith('import ') or stripped.startswith('from '):
                imports.append(stripped)
            else:
                non_import_lines.append(line)
        
        return imports, '\n'.join(non_import_lines)
    
    def _add_imports_to_file(self, file_code: str, imports: List[str]) -> str:
        """Add imports at file level after existing imports"""
        lines = file_code.split('\n')
        
        # Find last import line
        last_import_idx = -1
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('import ') or stripped.startswith('from '):
                last_import_idx = i
        
        # Add new imports after last existing import
        if last_import_idx >= 0:
            for imp in imports:
                # Check if import already exists
                if imp not in file_code:
                    lines.insert(last_import_idx + 1, imp)
                    last_import_idx += 1
        else:
            # No imports yet, add after docstring
            insert_idx = 0
            if lines and lines[0].strip().startswith('"""'):
                # Find end of docstring
                for i in range(1, len(lines)):
                    if '"""' in lines[i]:
                        insert_idx = i + 1
                        break
            
            for imp in imports:
                if imp not in file_code:
                    lines.insert(insert_idx, imp)
                    insert_idx += 1
        
        return '\n'.join(lines)
