"""
System Analyzer - Provides real context to LLM for improvement proposals
"""
import os
import json
from pathlib import Path
from typing import Dict, List, Optional

from shared.config.branding import get_platform_name

class SystemAnalyzer:
    def __init__(self, repo_path: str = "."):
        self.repo_path = Path(repo_path)
        from infrastructure.logging.logging_system import get_logger
        from shared.config.config_manager import get_config
        self.logger = get_logger("system_analyzer")
        self.config = get_config()
    
    def get_codebase_context(self) -> Dict:
        """Get overview of codebase structure and key files"""
        context = {
            "structure": self._get_directory_structure(),
            "key_files": self._get_key_files(),
            "test_coverage": self._analyze_test_coverage(),
            "capabilities": self._list_current_capabilities()
        }
        return context
    
    def _get_directory_structure(self) -> Dict:
        """Get directory structure"""
        structure = {}
        for root, dirs, files in os.walk(self.repo_path):
            # Skip ignored directories
            dirs[:] = [d for d in dirs if d not in ['__pycache__', 'node_modules', '.git', 'venv', 'checkpoints', 'backups']]
            
            rel_path = os.path.relpath(root, self.repo_path)
            if rel_path == '.':
                rel_path = 'root'
            
            py_files = [f for f in files if f.endswith('.py')]
            if py_files:
                structure[rel_path] = py_files
        
        return structure
    
    def _get_key_files(self) -> Dict[str, str]:
        """Get content of key system files"""
        key_files = {
            "core/immutable_brain_stem.py": "Safety validation rules",
            "tools/enhanced_filesystem_tool.py": "File operations tool",
            "planner/llm_client.py": "LLM integration",
            "core/improvement_loop.py": "Self-improvement loop"
        }
        
        file_contents = {}
        for file_path, description in key_files.items():
            full_path = self.repo_path / file_path
            if full_path.exists():
                try:
                    with open(full_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        max_chars = self.config.improvement.code_preview_chars
                        if len(content) > max_chars:
                            content = content[:max_chars] + "\n... (truncated)"
                        file_contents[file_path] = {
                            "description": description,
                            "content": content,
                            "lines": len(content.split('\n'))
                        }
                except Exception as e:
                    self.logger.error(f"Error reading {file_path}: {e}")
        
        return file_contents
    
    def _analyze_test_coverage(self) -> Dict:
        """Analyze test coverage and parse failures"""
        tests_dir = self.repo_path / "tests" / "unit"
        test_files = []
        failures = []
        
        if tests_dir.exists():
            for file in tests_dir.glob("test_*.py"):
                test_files.append(file.name)
        
        # Parse recent test failures from logs
        log_file = self.repo_path / "logs" / "test_failures.log"
        if log_file.exists():
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    for line in f.readlines()[-10:]:
                        if "FAILED" in line:
                            failures.append(line.strip())
            except Exception as e:
                self.logger.error(f"Error reading test failures: {e}")
        
        return {
            "test_count": len(test_files),
            "test_files": test_files,
            "missing_tests": self._find_missing_tests(),
            "recent_failures": failures
        }
    
    def _find_missing_tests(self) -> List[str]:
        """Find Tool class modules without tests (skip utility scripts)"""
        missing = []
        
        # Check tools - only include Tool classes
        tools_dir = self.repo_path / "tools"
        if tools_dir.exists():
            for tool_file in tools_dir.glob("*.py"):
                if tool_file.name.startswith("_"):
                    continue
                
                # Check if it's a Tool class
                content = self.get_file_content(f"tools/{tool_file.name}")
                is_tool_class = content and 'class ' in content and 'def execute(' in content
                
                # Only suggest tests for Tool classes
                if is_tool_class:
                    test_name = f"test_{tool_file.stem}.py"
                    test_path = self.repo_path / "tests" / "unit" / test_name
                    if not test_path.exists():
                        missing.append(f"tools/{tool_file.name}")
        
        return missing
    
    def _list_current_capabilities(self) -> List[str]:
        """List current tool capabilities"""
        capabilities = []
        
        tools_dir = self.repo_path / "tools"
        if tools_dir.exists():
            for tool_file in tools_dir.glob("*_tool.py"):
                capabilities.append(tool_file.stem.replace("_tool", ""))
        
        return capabilities
    
    def get_error_logs(self) -> List[Dict]:
        """Get recent error logs"""
        logs_dir = self.repo_path / "logs"
        errors = []
        
        if logs_dir.exists():
            log_file = logs_dir / "cua.log"
            if log_file.exists():
                try:
                    with open(log_file, 'r', encoding='utf-8') as f:
                        lines = f.readlines()[-100:]  # Last 100 lines
                        for line in lines:
                            try:
                                log_entry = json.loads(line)
                                if log_entry.get('level') in ['error', 'critical']:
                                    errors.append(log_entry)
                            except json.JSONDecodeError as e:
                                self.logger.debug(f"Error parsing log line: {e}")
                except Exception as e:
                    self.logger.error(f"Error reading logs: {e}")
        
        return errors[-10:]  # Last 10 errors
    
    def suggest_improvements(self) -> List[Dict]:
        """Return empty - let LLM analyze and decide improvements"""
        return []
    
    def get_file_content(self, file_path: str) -> Optional[str]:
        """Get content of specific file with function signatures extracted"""
        full_path = self.repo_path / file_path
        if full_path.exists():
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception as e:
                self.logger.error(f"Error reading {file_path}: {e}")
        return None
    
    def get_tool_template(self, tool_type: str = "simple") -> str:
        """Get a working tool template as example"""
        if tool_type == "simple":
            return '''"""Example Tool - Template for creating new tools"""
from dataclasses import dataclass
from typing import Dict, Any
from tools.capability_registry import ToolCapability, ParameterType

@dataclass
class ExampleToolResult:
    success: bool
    data: Any
    error: str = ""

class ExampleTool:
    def __init__(self):
        self.name = "example_tool"
    
    def execute(self, operation: str, params: Dict) -> ExampleToolResult:
        """Execute tool operation"""
        try:
            if operation == "do_something":
                return self._do_something(params)
            return ExampleToolResult(False, None, f"Unknown operation: {operation}")
        except Exception as e:
            return ExampleToolResult(False, None, str(e))
    
    def _do_something(self, params: Dict) -> ExampleToolResult:
        """Implement specific operation"""
        value = params.get('value')
        if not value:
            return ExampleToolResult(False, None, "Missing 'value' parameter")
        
        # Do actual work here
        result = f"Processed: {value}"
        return ExampleToolResult(True, result)
    
    def register_capabilities(self) -> list:
        """Register tool capabilities"""
        return [
            ToolCapability(
                name="do_something",
                description="Does something with a value",
                parameters={
                    "value": ParameterType.STRING
                },
                required_params=["value"]
            )
        ]
'''
        return ""
    
    def get_test_template(self) -> str:
        """Get generic test template - LLM decides what to test"""
        return '''"""Test template - adapt for your tool"""
import pytest
from tools.tool_result import ToolResult, ResultStatus

def test_tool_success():
    """Test successful operation"""
    # Import your tool
    # Create instance
    # Call execute() with operation and params
    # Assert result.status == ResultStatus.SUCCESS
    pass

def test_tool_failure():
    """Test failure case"""
    # Test with invalid params or operation
    # Assert result.status == ResultStatus.FAILURE
    pass
'''
    
    def get_file_signatures(self, file_path: str) -> List[str]:
        """Extract function/class signatures with actual code snippets"""
        import ast
        signatures = []
        
        content = self.get_file_content(file_path)
        if not content:
            return signatures
        
        try:
            lines = content.split('\n')
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    # Get class with first few lines
                    start = node.lineno - 1
                    end = min(start + 5, len(lines))
                    snippet = '\n'.join(lines[start:end])
                    signatures.append(snippet)
                elif isinstance(node, ast.FunctionDef) and not node.name.startswith('_'):
                    # Get function with first few lines
                    start = node.lineno - 1
                    end = min(start + 4, len(lines))
                    snippet = '\n'.join(lines[start:end])
                    signatures.append(snippet)
        except:
            pass
        
        return signatures[:5]  # Limit to 5 snippets
    
    def build_llm_context(self, focus: Optional[str] = None) -> str:
        """Build comprehensive context for LLM to analyze and decide"""
        context = self.get_codebase_context()
        errors = self.get_error_logs()
        
        prompt = f"""# {get_platform_name()} - Analysis Context

## Current Structure:
{json.dumps(context['structure'], indent=2)}

## Current Capabilities:
{', '.join(context['capabilities'])}

## Test Coverage:
- Total tests: {context['test_coverage']['test_count']}
- Test files: {', '.join(context['test_coverage']['test_files'])}
- Files without tests: {', '.join(context['test_coverage']['missing_tests'])}

## Recent Errors:
{json.dumps(errors[-3:], indent=2) if errors else 'No recent errors'}

## Your Task:
Analyze this codebase and decide what improvements would be most valuable.
Consider:
- System stability and reliability
- Code quality and maintainability  
- Missing functionality or capabilities
- Error patterns and failure points
- Architecture improvements

Propose ONE specific improvement with:
- Clear description of what and why
- Which file(s) to modify or create
- Expected benefit to the system

## Rules:
1. COPY exact imports/classes from existing code
2. NO placeholder code or comments
3. Tests go in tests/ directory ONLY
4. DO NOT modify core/immutable_brain_stem.py
5. Generate COMPLETE working code
"""
        
        if focus:
            prompt += f"\n## USER FOCUS: {focus}\n"
        
        return prompt
