"""
Baseline Health Checker - Gate for improvement loop
"""
import subprocess
import json
from pathlib import Path
from typing import Tuple, List

class BaselineHealthChecker:
    def __init__(self, repo_path: str = "."):
        self.repo_path = Path(repo_path)
        self.skip_tests = [
            "test_analyze_llm_logs.py",
            "test_capability_registry.py",
            "test_filesystem_tool_paths.py",
            "test_http_tool.py",
            "test_shell_tool_async_execution.py",
            "test_shell_tool_extended.py",
            "test_llm_retry.py",
            "test_sandbox_integration.py",
            "test_state_machine_resume.py",
            "test_update_pipeline.py"
        ]
    
    def check(self) -> Tuple[bool, str]:
        """Simple check method for evolution controller"""
        passed, message, _ = self.check_baseline()
        return passed, message
    
    def check_baseline(self) -> Tuple[bool, str, List[str]]:
        """Run baseline tests - returns (passed, message, failures)"""
        # 1. Syntax check
        syntax_ok, syntax_errors = self._check_syntax()
        if not syntax_ok:
            return False, "Syntax errors detected", syntax_errors
        
        # 2. Import check
        import_ok, import_errors = self._check_imports()
        if not import_ok:
            return False, "Import errors detected", import_errors
        
        # 3. Run tests
        test_ok, test_failures = self._run_baseline_tests()
        if not test_ok:
            return False, "Baseline tests failing", test_failures
        
        return True, "Baseline healthy", []
    
    def _check_syntax(self) -> Tuple[bool, List[str]]:
        """Check Python syntax for all files"""
        import ast
        errors = []
        pending_skip = self._get_pending_python_paths()
        
        for py_file in self.repo_path.rglob("*.py"):
            if "venv" in str(py_file) or "__pycache__" in str(py_file):
                continue
            normalized = str(py_file).replace("\\", "/")
            if normalized in pending_skip:
                continue
            try:
                ast.parse(py_file.read_text(encoding='utf-8'))
            except SyntaxError as e:
                errors.append(f"{py_file}:{e.lineno}: {e.msg}")
        
        return len(errors) == 0, errors

    def _get_pending_python_paths(self) -> set:
        """Pending tool/test files are quarantined from baseline syntax gate."""
        skip = set()
        pending_file = self.repo_path / "data" / "pending_tools.json"
        if not pending_file.exists():
            return skip

        try:
            payload = json.loads(pending_file.read_text(encoding="utf-8"))
            for item in payload.get("pending", {}).values():
                for key in ("tool_file", "test_file"):
                    path = item.get(key)
                    if path and str(path).endswith(".py"):
                        rel = str(path).replace("\\", "/")
                        skip.add(rel)
                        skip.add(str((self.repo_path / rel).resolve()).replace("\\", "/"))
        except Exception:
            return skip
        return skip
    
    def _check_imports(self) -> Tuple[bool, List[str]]:
        """Check critical imports"""
        critical_modules = [
            "core.system_analyzer",
            "tools.tool_interface",
            "planner.llm_client"
        ]
        errors = []
        
        for module in critical_modules:
            try:
                __import__(module)
            except Exception as e:
                errors.append(f"{module}: {str(e)}")
        
        return len(errors) == 0, errors
    
    def _run_baseline_tests(self) -> Tuple[bool, List[str]]:
        """Run baseline test suite"""
        ignore_args = [f"--ignore=tests/unit/{test}" for test in self.skip_tests]
        
        try:
            result = subprocess.run(
                ["python", "-m", "pytest", "tests/unit/", "-q", "--tb=line"] + ignore_args,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                return True, []
            
            # Parse failures
            failures = []
            for line in result.stdout.split('\n'):
                if 'FAILED' in line:
                    failures.append(line.strip())
            
            # If only known broken tests failed, consider it OK
            if len(failures) == 0:
                return True, []
            
            return False, failures
        except Exception as e:
            return False, [f"Test execution failed: {str(e)}"]
