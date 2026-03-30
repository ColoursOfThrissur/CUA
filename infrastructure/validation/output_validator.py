"""
Output Validator - Enforce strict contracts on LLM responses
"""
import ast
import json
from typing import Optional, Dict, Any

class OutputValidator:
    @staticmethod
    def validate_json(response: str, required_fields: list) -> Optional[Dict[str, Any]]:
        """Validate JSON response has required fields"""
        try:
            data = json.loads(response)
            for field in required_fields:
                if field not in data:
                    return None
            return data
        except:
            return None
    
    @staticmethod
    def validate_method_code(code: str) -> tuple[bool, str]:
        """Validate method code is single method, valid Python"""
        if not code.strip():
            return False, "Empty code"

        stripped = code.strip()
        if stripped.startswith("{") and ("method_code" in stripped or "\\n" in stripped):
            return False, "JSON-wrapped code"
        
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"Syntax error: {e}"
        
        # Find functions at top level OR inside classes
        functions = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                functions.append(node)
        
        if len(functions) == 0:
            return False, "No function definition found"

        # Reject duplicate function names in the same payload (usually malformed merges).
        names = [f.name for f in functions]
        if len(names) != len(set(names)):
            return False, "Duplicate function definitions found"
        
        # For single function, validate it
        if len(functions) == 1:
            func = functions[0]
            
            # Must have body
            if not func.body:
                return False, "Empty method body"
            
            # Check for placeholder patterns
            if len(func.body) == 1:
                node = func.body[0]
                if isinstance(node, ast.Pass):
                    return False, "Contains only 'pass'"
                if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                    if node.value.value in ["TODO", "...", "NotImplemented"]:
                        return False, "Contains placeholder"
        
        # Multiple functions are OK if it's a complete file with class
        return True, "Valid"
    
    @staticmethod
    def validate_task_analysis(data: dict) -> bool:
        """Validate task analysis output"""
        required = ["task_type", "target_file", "description", "methods_to_modify", "max_lines_expected", "category"]
        if not all(k in data for k in required):
            return False
        
        # Validate category
        allowed_categories = [
            "input_validation", "error_handling", "logging",
            "security", "timeout_handling", "parameter_validation",
            "performance", "refactoring"
        ]
        category = data.get("category", "")
        if category not in allowed_categories:
            # Allow 'safety' and 'performance' if they map to allowed
            if category not in ["safety"]:
                return False
        
        # Reject vague descriptions
        desc = data.get("description", "").lower()
        vague_terms = ["improve", "enhance", "better", "all parameters", "overall"]
        if any(term in desc for term in vague_terms) and len(desc) < 50:
            return False

        # Validate constraints
        max_lines = data.get("max_lines_expected", 999)
        if max_lines > 80:
            return False

        methods = data.get("methods_to_modify", [])
        if len(methods) > 3:
            return False
        
        return True
