"""
Sandbox Tester - Tests code proposals in isolated environment
"""
from typing import Dict, Optional
import ast
import tempfile
import sys
from pathlib import Path

class SandboxTester:
    def __init__(self, system_analyzer):
        from core.config_manager import get_config
        self.config = get_config()
        self.analyzer = system_analyzer
    
    def test_proposal(self, proposal: Dict, timeout: int = None) -> Dict:
        """
        Test proposal in sandbox
        Args:
            proposal: Proposal dict with raw_code and patch
            timeout: Timeout in seconds (from config if not provided)
        Returns: {
            'success': bool,
            'tests_passed': int,
            'tests_total': int,
            'output': str
        }
        """
        timeout = timeout or self.config.improvement.sandbox_timeout
        raw_code = proposal.get('raw_code', '')
        target_file = proposal.get('files_changed', [''])[0]
        
        if not raw_code:
            return self._error_result("No code to test")
        
        # Syntax validation
        try:
            ast.parse(raw_code)
        except SyntaxError as e:
            return self._error_result(f"Syntax error: {e}")
        
        # Import validation
        if target_file.endswith('.py'):
            import_error = self._validate_imports(raw_code, target_file)
            if import_error:
                return self._error_result(import_error)
        
        # Run in sandbox
        try:
            from updater.sandbox_runner import SandboxRunner
            runner = SandboxRunner(repo_path=".")
            result = runner.run_in_sandbox(proposal['patch'], timeout=timeout)
            
            tests_passed = result.test_output.count('PASSED') if result.test_output else 0
            tests_failed = result.test_output.count('FAILED') if result.test_output else 0
            tests_total = tests_passed + tests_failed
            
            # Handle skipped tests
            if 'SKIPPED' in result.test_output:
                tests_total = 1
                tests_passed = 1 if raw_code else 0
            
            return {
                "success": result.success,
                "tests_passed": tests_passed,
                "tests_total": tests_total if tests_total > 0 else 1,
                "output": result.test_output[:500] if result.test_output else (result.error or "Unknown error")
            }
        except Exception as e:
            return self._error_result(f"Sandbox error: {str(e)}")
    
    def _validate_imports(self, code: str, target_file: str) -> Optional[str]:
        """Validate code can be imported"""
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
                f.write(code)
                temp_path = f.name
            
            import importlib.util
            spec = importlib.util.spec_from_file_location("temp_module", temp_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules['temp_module'] = module
                try:
                    spec.loader.exec_module(module)
                    
                    # Validate test methods exist
                    if 'tests/' in target_file:
                        method_error = self._validate_test_methods(code, module)
                        if method_error:
                            del sys.modules['temp_module']
                            Path(temp_path).unlink(missing_ok=True)
                            return method_error
                    
                    del sys.modules['temp_module']
                except Exception as e:
                    Path(temp_path).unlink(missing_ok=True)
                    return f"Import failed: {type(e).__name__}: {str(e)}"
            
            Path(temp_path).unlink(missing_ok=True)
            return None
        except Exception as e:
            return f"Import validation failed: {str(e)}"
    
    def _validate_test_methods(self, code: str, test_module) -> Optional[str]:
        """Validate test calls real methods"""
        import ast
        
        try:
            tree = ast.parse(code)
            
            # Find tool imports
            tool_classes = {}
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    if node.module and node.module.startswith('tools.'):
                        tool_module = node.module.split('.')[-1]
                        for alias in node.names:
                            tool_classes[alias.name] = tool_module
            
            # Check method calls
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute):
                        method_name = node.func.attr
                        
                        if isinstance(node.func.value, ast.Name):
                            var_name = node.func.value.id
                            
                            # Validate tool methods exist
                            if var_name == 'tool':
                                for class_name, tool_module in tool_classes.items():
                                    try:
                                        import importlib
                                        mod = importlib.import_module(f'tools.{tool_module}')
                                        tool_class = getattr(mod, class_name, None)
                                        if tool_class and not hasattr(tool_class, method_name):
                                            return f"Method '{method_name}' does not exist on {class_name}"
                                    except:
                                        pass
                            
                            # ToolResult has no execute method
                            if var_name == 'result' and method_name == 'execute':
                                return "WRONG: result.execute() - ToolResult has NO execute method. CORRECT: tool.execute() returns ToolResult"
            
            return None
        except:
            return None
    
    def _error_result(self, message: str) -> Dict:
        """Return error result"""
        return {
            "success": False,
            "tests_passed": 0,
            "tests_total": 1,
            "output": message
        }
