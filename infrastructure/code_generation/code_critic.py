"""
Code Critic - Semantic validation of generated code
"""
import ast
import re
from typing import Optional, List, Tuple
from dataclasses import dataclass

@dataclass
class CriticResult:
    valid: bool
    confidence: float  # 0.0 to 1.0
    issues: List[str]
    warnings: List[str]

class CodeCritic:
    """Semantic validator for generated code"""
    
    def __init__(self):
        self.confidence_threshold = 0.7
    
    def critique(self, code: str, original_code: str, method_name: str) -> CriticResult:
        """Perform semantic validation on generated code"""
        issues = []
        warnings = []
        confidence = 1.0
        
        # Parse both versions
        try:
            new_tree = ast.parse(code)
            old_tree = ast.parse(original_code)
        except SyntaxError as e:
            return CriticResult(False, 0.0, [f"Syntax error: {e}"], [])
        
        # HARD FAILS - immediate rejection
        if self._has_empty_methods(new_tree):
            return CriticResult(False, 0.0, ["Empty method body detected"], [])
        
        security_issues = self._check_security_smells(code)
        if security_issues:
            return CriticResult(False, 0.0, security_issues, [])
        
        if self._has_placeholders(code):
            return CriticResult(False, 0.0, ["Incomplete implementation (TODO/NotImplementedError)"], [])
        
        drift = self._check_behavior_drift(old_tree, new_tree, method_name)
        if drift and "Return type changed" in drift:
            return CriticResult(False, 0.0, [f"Breaking change: {drift}"], [])
        
        dep_violations = self._check_dependency_violations(code)
        if dep_violations:
            return CriticResult(False, 0.0, dep_violations, [])
        
        # SOFT WARNINGS - lower confidence but don't reject
        redundancy = self._check_redundancy(new_tree)
        if redundancy:
            warnings.append(f"Redundant code: {redundancy}")
            confidence -= 0.1
        
        dead_code = self._check_dead_code(new_tree)
        if dead_code:
            warnings.append(f"Unreachable code: {dead_code}")
            confidence -= 0.15
        
        if drift and "New exceptions" in drift:
            warnings.append(f"Behavior change: {drift}")
            confidence -= 0.2
        
        valid = len(issues) == 0 and confidence >= self.confidence_threshold
        
        return CriticResult(valid, max(0.0, confidence), issues, warnings)
    
    def _has_empty_methods(self, tree: ast.Module) -> bool:
        """Check for methods with empty bodies"""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if not node.body or (len(node.body) == 1 and isinstance(node.body[0], ast.Pass)):
                    return True
        return False
    
    def _check_redundancy(self, tree: ast.Module) -> Optional[str]:
        """Check for duplicate logic"""
        # Check for duplicate if conditions
        conditions = []
        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                cond_str = ast.unparse(node.test)
                if cond_str in conditions:
                    return f"Duplicate condition: {cond_str}"
                conditions.append(cond_str)
        return None
    
    def _check_dead_code(self, tree: ast.Module) -> Optional[str]:
        """Check for unreachable code"""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for i, stmt in enumerate(node.body):
                    if isinstance(stmt, ast.Return) and i < len(node.body) - 1:
                        return f"Code after return in {node.name}"
        return None
    
    def _check_security_smells(self, code: str) -> List[str]:
        """Check for security anti-patterns"""
        issues = []
        
        # Hardcoded secrets
        if re.search(r'(password|secret|api_key|token)\s*=\s*["\'][^"\']+["\']', code, re.I):
            issues.append("Hardcoded secret detected")
        
        # Weak validation
        if 'if domain in url' in code or 'if domain in parsed' in code:
            issues.append("Weak URL validation (substring matching)")
        
        # SQL injection patterns
        if re.search(r'execute\([^)]*\+[^)]*\)', code) and 'sql' in code.lower():
            issues.append("Potential SQL injection")
        
        return issues
    
    def _check_behavior_drift(self, old_tree: ast.Module, new_tree: ast.Module, method_name: str) -> Optional[str]:
        """Check for undeclared behavior changes"""
        old_method = self._find_method(old_tree, method_name)
        new_method = self._find_method(new_tree, method_name)
        
        if not old_method or not new_method:
            return None
        
        # Check return type changes
        old_returns = self._get_return_types(old_method)
        new_returns = self._get_return_types(new_method)
        
        if old_returns != new_returns:
            return f"Return type changed: {old_returns} → {new_returns}"
        
        # Check exception changes
        old_raises = self._get_raised_exceptions(old_method)
        new_raises = self._get_raised_exceptions(new_method)
        
        new_exceptions = new_raises - old_raises
        if new_exceptions:
            return f"New exceptions raised: {new_exceptions}"
        
        return None
    
    def _find_method(self, tree: ast.Module, method_name: str) -> Optional[ast.FunctionDef]:
        """Find method by name"""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == method_name:
                return node
        return None
    
    def _get_return_types(self, method: ast.FunctionDef) -> set:
        """Extract return statement types"""
        returns = set()
        for node in ast.walk(method):
            if isinstance(node, ast.Return) and node.value:
                returns.add(type(node.value).__name__)
        return returns
    
    def _get_raised_exceptions(self, method: ast.FunctionDef) -> set:
        """Extract raised exception types"""
        exceptions = set()
        for node in ast.walk(method):
            if isinstance(node, ast.Raise) and node.exc:
                if isinstance(node.exc, ast.Call) and isinstance(node.exc.func, ast.Name):
                    exceptions.add(node.exc.func.id)
        return exceptions
    
    def _check_dependency_violations(self, code: str) -> List[str]:
        """Check for importing protected modules"""
        issues = []
        
        protected_imports = [
            'core.immutable_brain_stem',
            'core.session_permissions',
            'core.plan_schema'
        ]
        
        for protected in protected_imports:
            if f'from {protected}' in code or f'import {protected}' in code:
                issues.append(f"Importing protected module: {protected}")
        
        return issues
    
    def _has_placeholders(self, code: str) -> bool:
        """Check for incomplete implementation markers"""
        markers = [
            'raise NotImplementedError',
            '# TODO',
            '# FIXME',
            '# ... existing code',
            '# ... rest of',
            'pass  # TODO'
        ]
        return any(marker in code for marker in markers)
