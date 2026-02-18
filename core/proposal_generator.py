"""
Proposal Generator - Generates code proposals with validation
"""
from typing import Optional, Dict, Tuple
from pathlib import Path

class ProposalGenerator:
    def __init__(self, llm_client, system_analyzer, patch_generator, update_orchestrator):
        from core.config_manager import get_config
        self.config = get_config()
        self.llm_client = llm_client
        self.analyzer = system_analyzer
        self.patch_gen = patch_generator
        self.update_orchestrator = update_orchestrator
        self.previous_errors = []  # Track errors for learning
        
        # Create code generator
        from core.orchestrated_code_generator import OrchestratedCodeGenerator
        self.code_generator = OrchestratedCodeGenerator(llm_client, system_analyzer)
    
    def add_error(self, error: str):
        """Add error with size limit"""
        self.previous_errors.append(error)
        max_errors = self.config.improvement.max_error_history
        if len(self.previous_errors) > max_errors:
            self.previous_errors = self.previous_errors[-max_errors:]
    
    def clear_errors(self):
        """Clear error history"""
        self.previous_errors = []
    
    def generate_proposal(self, analysis: Dict) -> Optional[Dict]:
        """
        Generate code proposal from analysis
        Returns: {
            'description': str,
            'files_changed': [str],
            'diff_lines': int,
            'patch': str,
            'raw_code': str
        }
        """
        files_affected = analysis.get('files_affected', [])
        if not files_affected or not files_affected[0]:
            return None
        
        target_file = files_affected[0]
        target_tool = analysis.get('target_tool')
        
        # Generate code using code generator with error context
        success, raw_code, error = self.code_generator.generate_code(
            analysis['suggestion'],
            target_file,
            target_tool=target_tool,
            previous_errors=self.previous_errors
        )
        
        if not success:
            # If code generation failed, try self-correction once
            if raw_code and error and 'indent' in error.lower():
                success, raw_code, error = self._try_self_correction(raw_code, error, analysis['suggestion'], target_file)
            
            # CRITICAL: Do not proceed if still failed after self-correction
            if not success:
                # Track error for next attempt
                if error:
                    self.previous_errors.append(error)
                return None  # Return None to prevent broken code from being applied
        
        # Validate code
        validation_error = self._validate_code(raw_code, target_file)
        if validation_error:
            # Track validation error
            self.previous_errors.append(f"Validation: {validation_error}")
            # Only block on critical errors
            if "BLOCKED:" in validation_error or "Syntax error" in validation_error:
                return None
        
        # Generate patch
        patch = self.patch_gen.parse_llm_changes(f"```python\n{raw_code}\n```", target_file)
        if not patch:
            return None
        
        return {
            "description": analysis['suggestion'],
            "files_changed": [target_file],
            "diff_lines": len(patch.split('\n')),
            "patch": patch,
            "raw_code": raw_code
        }
    
    def _validate_code(self, code: str, file_path: str) -> Optional[str]:
        """Validate generated code with security pattern checks"""
        import ast
        
        if not file_path.endswith('.py'):
            return None
        
        # CRITICAL: Reject JSON-like responses (LLM confusion)
        if code.strip().startswith('{') and '"modified_method"' in code:
            return "BLOCKED: LLM returned JSON instead of Python code"
        
        # Protected files from config
        protected_files = self.config.improvement.protected_files
        
        for protected in protected_files:
            if protected in file_path.replace('\\', '/'):
                return f"BLOCKED: {file_path} is protected"
        
        # Syntax validation
        try:
            ast.parse(code)
        except SyntaxError as e:
            return f"Syntax error line {e.lineno}: {e.msg}"
        except Exception as e:
            return f"Parse error: {str(e)}"
        
        # CRITICAL: Check for security anti-patterns
        security_issues = self._check_security_patterns(code, file_path)
        if security_issues:
            return f"BLOCKED: {security_issues}"
        
        # Dangerous patterns
        dangerous = ['eval(', 'exec(', '__import__', 'compile(']
        for pattern in dangerous:
            if pattern in code:
                return f"Dangerous pattern: {pattern}"
        
        # Check for incomplete code
        lines = code.split('\n')
        for i, line in enumerate(lines, 1):
            if 'raise NotImplementedError' in line:
                return f"Line {i}: Incomplete implementation"
            if '# ... existing code ...' in line.lower() or '# ... rest of' in line.lower():
                return f"Line {i}: Placeholder comment"
        
        # Test code in production files
        if 'tests/' not in file_path and 'test_' not in file_path:
            test_indicators = ['import unittest', 'import pytest', 'class Test', 'def test_']
            for indicator in test_indicators:
                if indicator in code:
                    return f"Test code in production file: {indicator}"
        
        # Pytest style for tests
        if 'tests/' in file_path and 'test_' in file_path:
            if 'import unittest' in code or 'unittest.TestCase' in code:
                return "Use pytest instead of unittest"
        
        return None
    
    def _check_security_patterns(self, code: str, file_path: str) -> Optional[str]:
        """Check for security anti-patterns that should never be allowed"""
        
        # SSRF vulnerability patterns - substring matching in URL validation
        if any(func in code for func in ['_is_allowed_url', 'validate_url', 'check_url']):
            # Check for weak validation patterns
            weak_patterns = [
                ('domain in parsed.netloc', 'Use exact domain matching: parsed.netloc == domain or parsed.netloc.endswith("." + domain)'),
                ('domain in url', 'Use exact domain matching with urlparse'),
                (' in parsed.netloc', 'Substring matching in URL validation is vulnerable to SSRF'),
            ]
            
            for pattern, fix in weak_patterns:
                if pattern in code:
                    return f"SSRF vulnerability: {pattern}. Fix: {fix}"
        
        # SQL injection patterns
        if 'execute(' in code and any(x in code for x in ['f"', "f'", ' + ']):
            if 'sql' in code.lower() or 'query' in code.lower():
                return "Potential SQL injection - use parameterized queries"
        
        # Path traversal without validation
        if 'open(' in code or 'Path(' in code:
            if '_validate_path' not in code and 'validate' not in file_path:
                # Only warn for tools that handle user input
                if 'tool' in file_path.lower():
                    return "File operations without path validation in tool"
        
        return None
    
    def _try_self_correction(self, broken_code: str, error: str, task: str, target_file: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """Let LLM fix its own indentation errors"""
        from core.logging_system import get_logger
        logger = get_logger("proposal_generator")
        logger.info("Attempting to fix indentation error...")
        
        # Show LLM its broken code with line numbers
        lines = broken_code.split('\n')
        numbered_code = '\n'.join([f"{i+1:3d}: {line}" for i, line in enumerate(lines)])
        
        prompt = self.llm_client._format_prompt(f"""Your previous code has an indentation error. Fix it.

TASK: {task}
FILE: {target_file}
ERROR: {error}

YOUR BROKEN CODE (with line numbers):
```python
{numbered_code}
```

RULES:
1. Fix ONLY the indentation - use 4 spaces consistently
2. Do NOT change the logic
3. Do NOT use tabs
4. Output COMPLETE corrected code
5. Remove line numbers from output

Output the FIXED code:""")
        
        response = self.llm_client._call_llm(prompt, temperature=0.1)
        if not response:
            return False, broken_code, "Self-correction failed: no response"
        
        # Extract fixed code
        fixed_code = None
        if '```python' in response:
            start = response.find('```python') + 9
            end = response.find('```', start)
            if end != -1:
                fixed_code = response[start:end].strip()
        elif '```' in response:
            start = response.find('```') + 3
            end = response.find('```', start)
            if end != -1:
                fixed_code = response[start:end].strip()
        
        if not fixed_code:
            return False, broken_code, "Self-correction failed: no code extracted"
        
        # Remove line numbers if LLM included them
        import re
        lines = fixed_code.split('\n')
        cleaned = []
        for line in lines:
            # Remove leading line numbers like "  1: " or "123: "
            cleaned_line = re.sub(r'^\s*\d+:\s*', '', line)
            cleaned.append(cleaned_line)
        fixed_code = '\n'.join(cleaned)
        
        # Validate fixed code
        try:
            import ast
            ast.parse(fixed_code)
            logger.info("Success - indentation fixed")
            return True, fixed_code, None
        except Exception as e:
            return False, broken_code, f"Self-correction failed: {str(e)}"
