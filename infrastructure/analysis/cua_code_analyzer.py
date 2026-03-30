"""Context-aware code analyzer for CUA tools - understands thin tool pattern"""
import ast
import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

@dataclass
class CodeIssue:
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    type: str
    description: str
    line: Optional[int] = None
    suggestion: Optional[str] = None

class CUACodeAnalyzer:
    """Analyzes tool code with awareness of CUA architecture"""
    
    def __init__(self):
        from infrastructure.external.service_registry import SERVICE_METHODS
        self.service_methods = SERVICE_METHODS
        self.hardcoded_patterns = [
            (r'http://example\.com', 'Hardcoded example.com URL'),
            (r'navigate\(["\']http[^"\']*example', 'Hardcoded example URL in navigate'),
            (r'test_user|demo_user', 'Hardcoded test username'),
            (r'password\s*=\s*["\'][^"\']+["\']', 'Hardcoded password'),
        ]
    
    def analyze(self, code: str, tool_spec: Optional[Dict] = None) -> List[CodeIssue]:
        """Analyze code and return issues"""
        issues = []
        
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return [CodeIssue('CRITICAL', 'syntax', f'Syntax error: {e}', e.lineno)]
        
        # Check capability-spec match
        if tool_spec:
            issues.extend(self._check_capability_match(tree, tool_spec))
        
        # Check service usage
        issues.extend(self._check_service_usage(tree, code))
        
        # Check hardcoded values
        issues.extend(self._check_hardcoded_values(code))
        
        # Check return types
        issues.extend(self._check_return_types(tree))
        
        return issues
    
    def _check_capability_match(self, tree: ast.AST, tool_spec: Dict) -> List[CodeIssue]:
        """Check if handlers match capability definitions"""
        issues = []
        
        # Extract capabilities from spec
        capabilities = {}
        for input_spec in tool_spec.get('inputs', []):
            op_name = input_spec.get('operation')
            params = [p.get('name') for p in input_spec.get('parameters', []) if isinstance(p, dict)]
            capabilities[f'_handle_{op_name}'] = set(params)
        
        # Find class and handlers
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith('_handle_'):
                if node.name in capabilities:
                    # Check parameter usage
                    expected_params = capabilities[node.name]
                    used_params = self._get_used_kwargs(node)
                    
                    # Check for undefined params
                    for param in used_params:
                        if param not in expected_params:
                            issues.append(CodeIssue(
                                'HIGH',
                                'undefined_parameter',
                                f"Handler {node.name} uses parameter '{param}' not in capability definition",
                                node.lineno,
                                f"Add '{param}' to capability parameters or remove usage"
                            ))
        
        return issues
    
    def _check_service_usage(self, tree: ast.AST, code: str) -> List[CodeIssue]:
        """Check if service methods exist"""
        issues = []
        
        # Find service calls: self.services.X.Y()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    # Check if it's self.services.X.method()
                    if isinstance(node.func.value, ast.Attribute):
                        if isinstance(node.func.value.value, ast.Attribute):
                            if (isinstance(node.func.value.value.value, ast.Name) and
                                node.func.value.value.value.id == 'self' and
                                node.func.value.value.attr == 'services'):
                                
                                service_name = node.func.value.attr
                                method_name = node.func.attr
                                
                                # Check if service exists
                                if service_name not in self.service_methods:
                                    issues.append(CodeIssue(
                                        'HIGH',
                                        'unknown_service',
                                        f"Unknown service: self.services.{service_name}",
                                        node.lineno,
                                        f"Available services: {', '.join(self.service_methods.keys())}"
                                    ))
                                # Check if method exists
                                elif not any(method_name in m for m in self.service_methods[service_name]):
                                    issues.append(CodeIssue(
                                        'HIGH',
                                        'unknown_method',
                                        f"Unknown method: self.services.{service_name}.{method_name}()",
                                        node.lineno,
                                        f"Available methods: {', '.join(self.service_methods[service_name])}"
                                    ))
        
        return issues
    
    def _check_hardcoded_values(self, code: str) -> List[CodeIssue]:
        """Check for hardcoded test values"""
        issues = []
        
        for pattern, description in self.hardcoded_patterns:
            matches = re.finditer(pattern, code, re.IGNORECASE)
            for match in matches:
                # Get line number
                line_num = code[:match.start()].count('\n') + 1
                issues.append(CodeIssue(
                    'HIGH',
                    'hardcoded_value',
                    description,
                    line_num,
                    'Use parameter or configuration instead'
                ))
        
        return issues
    
    def _check_return_types(self, tree: ast.AST) -> List[CodeIssue]:
        """Check if handlers return dict (not ToolResult)"""
        issues = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith('_handle_'):
                # Check return statements
                for child in ast.walk(node):
                    if isinstance(child, ast.Return) and child.value:
                        # Check if returning ToolResult
                        if isinstance(child.value, ast.Call):
                            if isinstance(child.value.func, ast.Name):
                                if child.value.func.id == 'ToolResult':
                                    issues.append(CodeIssue(
                                        'HIGH',
                                        'wrong_return_type',
                                        f"Handler {node.name} returns ToolResult - should return plain dict",
                                        child.lineno,
                                        'Return dict like {\'success\': True, \'data\': ...}'
                                    ))
        
        return issues
    
    def _get_used_kwargs(self, func_node: ast.FunctionDef) -> set:
        """Extract kwargs.get() calls from function"""
        used = set()
        for node in ast.walk(func_node):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if (isinstance(node.func.value, ast.Name) and
                        node.func.value.id == 'kwargs' and
                        node.func.attr == 'get'):
                        # Get the parameter name
                        if node.args and isinstance(node.args[0], ast.Constant):
                            used.add(node.args[0].value)
        return used
