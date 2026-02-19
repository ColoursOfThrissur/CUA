"""
Refactoring permissions - allow internal improvements
"""
from dataclasses import dataclass
from typing import List
import ast

@dataclass
class RefactoringPermissions:
    max_file_lines: int = 200
    allow_method_extraction: bool = True
    allow_helper_classes: bool = True
    allow_private_state: bool = True
    allow_internal_restructure: bool = True
    block_public_api_changes: bool = True
    block_cross_file_mods: bool = True
    block_abstract_changes: bool = True
    
    def validate_refactoring(self, original_code: str, new_code: str) -> tuple[bool, str]:
        """Validate refactoring preserves contracts"""
        try:
            orig_tree = ast.parse(original_code)
            new_tree = ast.parse(new_code)
        except SyntaxError as e:
            return False, f"Syntax error: {e}"
        
        # Check file size
        new_lines = len(new_code.split('\n'))
        if new_lines > self.max_file_lines:
            return False, f"File too large: {new_lines} lines (max {self.max_file_lines})"
        
        # Check public API preservation
        if self.block_public_api_changes:
            orig_public = self._extract_public_api(orig_tree)
            new_public = self._extract_public_api(new_tree)
            
            if orig_public != new_public:
                return False, "Public API changed"
        
        # Check abstract methods
        if self.block_abstract_changes:
            if self._has_abstract_changes(orig_tree, new_tree):
                return False, "Abstract methods modified"
        
        return True, "Refactoring valid"
    
    def _extract_public_api(self, tree: ast.AST) -> set:
        """Extract public method signatures"""
        public_methods = set()
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if not node.name.startswith('_'):
                    # Get signature
                    args = [arg.arg for arg in node.args.args]
                    sig = f"{node.name}({','.join(args)})"
                    public_methods.add(sig)
        
        return public_methods
    
    def _has_abstract_changes(self, orig_tree: ast.AST, new_tree: ast.AST) -> bool:
        """Check if abstract methods were modified"""
        orig_abstract = self._find_abstract_methods(orig_tree)
        new_abstract = self._find_abstract_methods(new_tree)
        return orig_abstract != new_abstract
    
    def _find_abstract_methods(self, tree: ast.AST) -> set:
        """Find methods with @abstractmethod decorator"""
        abstract = set()
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Name) and decorator.id == 'abstractmethod':
                        abstract.add(node.name)
        
        return abstract
    
    def is_allowed_refactoring(self, refactor_type: str) -> bool:
        """Check if refactoring type is allowed"""
        allowed = {
            "method_extraction": self.allow_method_extraction,
            "helper_class": self.allow_helper_classes,
            "private_state": self.allow_private_state,
            "internal_restructure": self.allow_internal_restructure
        }
        return allowed.get(refactor_type, False)
