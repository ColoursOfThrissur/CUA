"""Dependency checker - detects missing libraries and services in generated code."""
import ast
import importlib.util
from typing import List, Dict, Set
from dataclasses import dataclass


@dataclass
class DependencyReport:
    """Report of missing dependencies."""
    missing_libraries: List[str]
    missing_services: List[str]
    all_imports: List[str]
    all_service_calls: List[str]
    is_valid: bool
    
    def has_missing(self) -> bool:
        return len(self.missing_libraries) > 0 or len(self.missing_services) > 0


class DependencyChecker:
    """Check code for missing dependencies."""
    
    # Available services in ToolServices
    AVAILABLE_SERVICES = {
        'storage', 'time', 'ids', 'llm', 'http', 'json', 'shell', 'fs', 'logging',
        'extract_key_points', 'sentiment_analysis', 'detect_language', 
        'generate_json_output', 'call_tool', 'list_tools', 'has_capability'
    }
    
    # Standard library modules (don't need installation)
    STDLIB_MODULES = {
        'json', 'os', 'sys', 'time', 'datetime', 'pathlib', 're', 'typing',
        'collections', 'itertools', 'functools', 'math', 'random', 'uuid',
        'logging', 'traceback', 'inspect', 'ast', 'dataclasses', 'enum'
    }
    
    def check_code(self, code: str) -> DependencyReport:
        """Check code for missing dependencies."""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return DependencyReport([], [], [], [], False)
        
        # Extract imports
        imports = self._extract_imports(tree)
        
        # Extract service calls
        service_calls = self._extract_service_calls(tree)
        
        # Check which are missing
        missing_libs = self._check_libraries(imports)
        missing_services = self._check_services(service_calls)
        
        return DependencyReport(
            missing_libraries=missing_libs,
            missing_services=missing_services,
            all_imports=imports,
            all_service_calls=service_calls,
            is_valid=True
        )
    
    def _extract_imports(self, tree: ast.AST) -> List[str]:
        """Extract all import statements."""
        imports = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module.split('.')[0])
        
        return list(set(imports))
    
    def _extract_service_calls(self, tree: ast.AST) -> List[str]:
        """Extract all self.services.X calls."""
        service_calls = set()
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                # Check for self.services.X pattern
                if isinstance(node.value, ast.Attribute):
                    if (isinstance(node.value.value, ast.Name) and 
                        node.value.value.id == 'self' and 
                        node.value.attr == 'services'):
                        service_calls.add(node.attr)
        
        return list(service_calls)
    
    def _check_libraries(self, imports: List[str]) -> List[str]:
        """Check which libraries are not installed."""
        missing = []
        
        for module in imports:
            # Skip standard library
            if module in self.STDLIB_MODULES:
                continue
            
            # Skip local imports (tools, core, etc.)
            if module in ['tools', 'core', 'api', 'planner', 'updater']:
                continue
            
            # Check if installed
            if not self._is_installed(module):
                missing.append(module)
        
        return missing
    
    def _check_services(self, service_calls: List[str]) -> List[str]:
        """Check which services don't exist."""
        missing = []
        
        for service in service_calls:
            if service not in self.AVAILABLE_SERVICES:
                missing.append(service)
        
        return missing
    
    def _is_installed(self, module: str) -> bool:
        """Check if module is installed."""
        try:
            spec = importlib.util.find_spec(module)
            return spec is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            return False
