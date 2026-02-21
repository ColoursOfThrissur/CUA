"""Validator for tool evolution - ensures no breaking changes."""
import ast
from typing import Tuple, Dict, Any
from core.enhanced_code_validator import EnhancedCodeValidator


class EvolutionValidator:
    """Validates evolved tool code."""
    
    def __init__(self):
        self.enhanced_validator = EnhancedCodeValidator()
    
    def validate(
        self,
        original_code: str,
        improved_code: str,
        proposal: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Validate improved code doesn't break interface."""
        
        # 0. Enhanced validation (truncation, undefined methods, uninitialized attrs)
        is_valid, error = self.enhanced_validator.validate(improved_code)
        if not is_valid:
            return False, f"Enhanced validation failed: {error}"
        
        # 1. Syntax check
        try:
            ast.parse(improved_code)
        except SyntaxError as e:
            return False, f"Syntax error: {e}"
        
        # 2. Extract class names from both
        original_classes = self._extract_class_names(original_code)
        improved_classes = self._extract_class_names(improved_code)
        
        # Class names must match (no renaming)
        if original_classes != improved_classes:
            return False, f"Class names changed: {original_classes} -> {improved_classes}"
        
        # 3. Extract public methods from both
        original_methods = self._extract_public_methods(original_code)
        improved_methods = self._extract_public_methods(improved_code)
        
        # All original public methods must exist (can add new ones)
        missing = original_methods - improved_methods
        if missing:
            return False, f"Public methods removed: {missing}"
        
        # 4. Required tool methods check
        if not self._has_required_methods(improved_code):
            return False, "Missing required methods (get_capabilities or execute)"
        
        return True, ""
    
    def _extract_class_names(self, code: str) -> set:
        """Extract class names from code."""
        try:
            tree = ast.parse(code)
            return {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
        except:
            return set()
    
    def _extract_public_methods(self, code: str) -> set:
        """Extract public method names from code."""
        try:
            tree = ast.parse(code)
            methods = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if not node.name.startswith('_'):
                        methods.add(node.name)
            return methods
        except:
            return set()
    
    def _has_required_methods(self, code: str) -> bool:
        """Check for required tool methods."""
        try:
            tree = ast.parse(code)
            methods = set()
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    methods.add(node.name)
            
            # Must have get_capabilities or register_capabilities, and execute
            has_capabilities = "get_capabilities" in methods or "register_capabilities" in methods
            has_execute = "execute" in methods
            
            return has_capabilities and has_execute
        except:
            return False
