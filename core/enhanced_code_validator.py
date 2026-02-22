"""Enhanced code validator - catches architectural issues missed by basic validation."""
import ast
import re
from typing import Tuple, Set, Dict, List, Optional

class EnhancedCodeValidator:
    """Validates code for architectural issues beyond syntax."""
    
    def __init__(self, available_services: Optional[List[str]] = None):
        """Initialize with list of available service methods."""
        self.available_services = available_services or [
            'storage', 'llm', 'http', 'fs', 'json', 'shell', 'time', 'ids', 'logging',
            'orchestrator', 'registry', 'extract_key_points', 'sentiment_analysis',
            'detect_language', 'generate_json_output', 'call_tool', 'list_tools', 'has_capability'
        ]
        # BaseTool inherited methods and attributes
        self.base_tool_methods = {
            'add_capability', 'get_capabilities', 'has_capability', 'execute_capability',
            'get_performance_stats', 'to_llm_description', 'register_capabilities', 'execute'
        }
        self.base_tool_attributes = {
            'name', 'capabilities', '_capabilities', '_performance_stats', 'description', 'services'
        }
        # Python built-in attributes
        self.builtin_attributes = {
            '__class__', '__dict__', '__doc__', '__module__', '__name__', '__bases__'
        }
    
    def validate(self, code: str, class_name: Optional[str] = None) -> Tuple[bool, str]:
        """Run all enhanced validations."""
        
        # 1. Check for truncation
        is_complete, truncation_error = self._check_truncation(code)
        if not is_complete:
            return False, truncation_error
        
        # 2. Parse AST
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"Syntax error: {e}"
        
        # 3. Find target class
        if class_name:
            target_class = self._find_class(tree, class_name)
            if not target_class:
                return False, f"Class '{class_name}' not found"
        else:
            # Find first class
            target_class = next((n for n in tree.body if isinstance(n, ast.ClassDef)), None)
            if not target_class:
                return False, "No class found in code"
        
        # 4. Check for undefined method calls
        is_valid, error = self._check_undefined_methods(target_class)
        if not is_valid:
            return False, error
        
        # 5. Check for uninitialized attributes
        is_valid, error = self._check_uninitialized_attributes(target_class)
        if not is_valid:
            return False, error
        
        # 6. Check service usage
        is_valid, error = self._check_service_usage(target_class)
        if not is_valid:
            return False, error
        
        return True, ""
    
    def _check_truncation(self, code: str) -> Tuple[bool, str]:
        """Check if code appears truncated."""
        lines = code.strip().splitlines()
        if not lines:
            return False, "Code is empty"
        
        last_line = lines[-1].strip()
        
        # Check for incomplete statements
        truncation_indicators = [
            r'^\s*if\s+.*:\s*$',  # if without body
            r'^\s*def\s+\w+\([^)]*$',  # incomplete function def
            r'^\s*\w+\s*=\s*$',  # incomplete assignment
            r'[,\(]$',  # ends with comma or open paren
            r'^\s*missing\s*=.*if\s+p\s+not\s+in\s+kwargs$',  # specific truncation pattern
        ]
        
        for pattern in truncation_indicators:
            if re.match(pattern, last_line):
                return False, f"Code appears truncated at: {last_line[:50]}"
        
        # Check for balanced braces/parens
        open_count = code.count('(') - code.count(')')
        if open_count > 0:
            return False, f"Unbalanced parentheses: {open_count} unclosed"
        
        bracket_count = code.count('[') - code.count(']')
        if bracket_count > 0:
            return False, f"Unbalanced brackets: {bracket_count} unclosed"
        
        brace_count = code.count('{') - code.count('}')
        if brace_count > 0:
            return False, f"Unbalanced braces: {brace_count} unclosed"
        
        return True, ""
    
    def _check_undefined_methods(self, target_class: ast.ClassDef) -> Tuple[bool, str]:
        """Check for calls to undefined methods."""
        # Get all defined methods in class
        defined_methods = {
            node.name for node in target_class.body 
            if isinstance(node, ast.FunctionDef)
        }
        
        # Get attributes initialized in __init__ (could be function references)
        init_method = next((m for m in target_class.body if isinstance(m, ast.FunctionDef) and m.name == '__init__'), None)
        initialized_attrs = set()
        if init_method:
            for node in ast.walk(init_method):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Attribute):
                            if isinstance(target.value, ast.Name) and target.value.id == 'self':
                                initialized_attrs.add(target.attr)
        
        # Check each method for calls to undefined methods
        for method in target_class.body:
            if not isinstance(method, ast.FunctionDef):
                continue
            
            for node in ast.walk(method):
                if not isinstance(node, ast.Call):
                    continue
                
                # Check for self.method_name() calls
                if isinstance(node.func, ast.Attribute):
                    if isinstance(node.func.value, ast.Name) and node.func.value.id == 'self':
                        called_method = node.func.attr
                        
                        # Skip if it's a service call (self.services.X)
                        if called_method == 'services':
                            continue
                        
                        # Skip if it's a known base class method
                        if called_method in self.base_tool_methods:
                            continue
                        
                        # Skip if it's an attribute assigned in __init__ (could be function reference)
                        if called_method in initialized_attrs:
                            continue
                        
                        # Check if method is defined
                        if called_method not in defined_methods:
                            return False, f"Method '{method.name}' calls undefined method 'self.{called_method}()'"
        
        return True, ""
    
    def _check_uninitialized_attributes(self, target_class: ast.ClassDef) -> Tuple[bool, str]:
        """Check for usage of uninitialized attributes."""
        # Get attributes initialized in __init__
        init_method = next((m for m in target_class.body if isinstance(m, ast.FunctionDef) and m.name == '__init__'), None)
        
        initialized_attrs = set()
        if init_method:
            for node in ast.walk(init_method):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Attribute):
                            if isinstance(target.value, ast.Name) and target.value.id == 'self':
                                initialized_attrs.add(target.attr)
        
        # Check all methods for attribute usage
        for method in target_class.body:
            if not isinstance(method, ast.FunctionDef):
                continue
            if method.name == '__init__':
                continue
            
            for node in ast.walk(method):
                # Check attribute reads
                if isinstance(node, ast.Attribute):
                    if isinstance(node.value, ast.Name) and node.value.id == 'self':
                        attr_name = node.attr
                        
                        # Skip known base class attributes and methods
                        if attr_name in self.base_tool_attributes or attr_name in self.base_tool_methods:
                            continue
                        
                        # Skip Python built-in attributes
                        if attr_name in self.builtin_attributes:
                            continue
                        
                        # Check if attribute is initialized
                        if attr_name not in initialized_attrs:
                            # Check if it's being assigned (not just read)
                            parent = self._get_parent_node(method, node)
                            if not (isinstance(parent, ast.Assign) and node in parent.targets):
                                # Check if it's a method call (parent is Call node)
                                if isinstance(parent, ast.Call):
                                    continue
                                return False, f"Method '{method.name}' uses uninitialized attribute 'self.{attr_name}'"
        
        return True, ""
    
    def _check_service_usage(self, target_class: ast.ClassDef) -> Tuple[bool, str]:
        """Check that service methods are called correctly."""
        for method in target_class.body:
            if not isinstance(method, ast.FunctionDef):
                continue
            
            for node in ast.walk(method):
                if not isinstance(node, ast.Call):
                    continue
                
                # Check for self.services.X.Y() pattern
                if isinstance(node.func, ast.Attribute):
                    if isinstance(node.func.value, ast.Attribute):
                        if (isinstance(node.func.value.value, ast.Name) and 
                            node.func.value.value.id == 'self' and 
                            node.func.value.attr == 'services'):
                            
                            service_name = node.func.attr
                            # This is a valid service call pattern
                            continue
                    
                    # Check for direct self.service_method() that should be self.services.method()
                    if isinstance(node.func.value, ast.Name) and node.func.value.id == 'self':
                        method_name = node.func.attr
                        
                        # Check if this looks like a service method
                        if method_name in self.available_services:
                            return False, f"Method '{method.name}' calls 'self.{method_name}()' but should use 'self.services.{method_name}()'"
        
        return True, ""
    
    def _get_parent_node(self, root, target):
        """Find parent node of target in AST."""
        for node in ast.walk(root):
            for child in ast.iter_child_nodes(node):
                if child is target:
                    return node
        return None
    
    def _find_class(self, tree: ast.Module, class_name: str) -> Optional[ast.ClassDef]:
        """Find class by name in AST."""
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                return node
        return None
