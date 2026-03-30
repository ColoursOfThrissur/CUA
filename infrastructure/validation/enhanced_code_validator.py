"""
Enhanced Code Validator - Advanced code validation with semantic checks
"""

import ast
from typing import Dict, Any, List, Optional


class EnhancedCodeValidator:
    """Enhanced validator with semantic and architectural checks."""
    
    def __init__(self):
        self.dangerous_patterns = [
            'eval', 'exec', '__import__', 'compile',
            'os.system', 'subprocess.Popen'
        ]
        self.required_patterns = [
            'class', 'def execute'
        ]
    
    def validate(self, code: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Validate code with enhanced checks."""
        errors = []
        warnings = []
        
        # Parse AST
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return {
                "valid": False,
                "errors": [f"Syntax error: {str(e)}"],
                "warnings": [],
                "score": 0
            }
        
        # Check for dangerous patterns
        for pattern in self.dangerous_patterns:
            if pattern in code:
                errors.append(f"Dangerous pattern detected: {pattern}")
        
        # Check for required patterns
        for pattern in self.required_patterns:
            if pattern not in code:
                warnings.append(f"Missing recommended pattern: {pattern}")
        
        # Check class structure
        classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
        if not classes:
            errors.append("No class definition found")
        
        # Check for execute method
        has_execute = False
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'execute':
                has_execute = True
                break
        
        if not has_execute:
            warnings.append("No execute method found")
        
        # Calculate score
        score = 100
        score -= len(errors) * 20
        score -= len(warnings) * 5
        score = max(0, min(100, score))
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "score": score
        }
    
    def validate_tool_code(self, code: str, tool_name: str) -> Dict[str, Any]:
        """Validate tool-specific code."""
        return self.validate(code, {"tool_name": tool_name})
