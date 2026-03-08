"""Enhanced code validator - catches architectural issues missed by basic validation."""
import ast
import re
from typing import Tuple, Set, Dict, List, Optional

class EnhancedCodeValidator:
    """Validates code for architectural issues beyond syntax."""
    
    def __init__(self, available_services: Optional[List[str]] = None, service_registry: Optional[Dict] = None):
        """Initialize with list of available service methods and service registry."""
        self.available_services = available_services or [
            'storage', 'llm', 'http', 'fs', 'json', 'shell', 'time', 'ids', 'logging',
            'orchestrator', 'registry', 'extract_key_points', 'sentiment_analysis',
            'detect_language', 'generate_json_output', 'call_tool', 'list_tools', 'has_capability', 'browser'
        ]
        # Service registry maps service names to their available methods
        self.service_registry = service_registry or {
            'storage': ['save', 'get', 'list', 'find', 'count', 'update', 'delete', 'exists'],
            'llm': ['generate'],
            'http': ['get', 'post', 'put', 'delete', 'request'],
            'fs': ['read', 'write', 'list', 'exists', 'delete', 'mkdir'],
            'json': ['parse', 'stringify', 'query'],
            'shell': ['execute'],
            'time': ['now_utc', 'now_local', 'now_utc_iso', 'now_local_iso'],
            'ids': ['generate', 'uuid'],
            'logging': ['info', 'warning', 'error', 'debug'],
            'browser': ['open_browser', 'navigate', 'find_element', 'get_page_text', 'take_screenshot', 'close', 'is_available']
        }
        self.missing_services = []  # Track missing services for generation
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
        
        # Reset missing services tracker
        self.missing_services = []
        
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
        
        # 6. Check service usage (detects missing services)
        is_valid, error = self._check_service_usage(target_class)
        if not is_valid:
            return False, error
        
        return True, ""
    
    def get_missing_services(self) -> List[Dict[str, str]]:
        """Get list of missing services detected during validation."""
        return self.missing_services
    
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
        """Check that service methods are called correctly and detect missing services."""
        errors = []
        
        for method in target_class.body:
            if not isinstance(method, ast.FunctionDef):
                continue
            
            for node in ast.walk(method):
                if not isinstance(node, ast.Call):
                    continue
                
                # Check for self.services.service_name.method_name() pattern
                if isinstance(node.func, ast.Attribute):
                    if isinstance(node.func.value, ast.Attribute):
                        if (isinstance(node.func.value.value, ast.Name) and 
                            node.func.value.value.id == 'self' and 
                            node.func.value.attr == 'services'):
                            
                            service_name = node.func.attr
                            
                            # Check if service exists in registry
                            if service_name not in self.service_registry:
                                # Unknown service - mark as missing
                                line_num = node.lineno if hasattr(node, 'lineno') else 0
                                self.missing_services.append({
                                    'service_name': service_name,
                                    'method_name': None,
                                    'line': line_num,
                                    'type': 'full_service'
                                })
                                errors.append(f"Unknown service: self.services.{service_name} (line {line_num})")
                            continue
                    
                    # Check for self.services.service_name.method_name() - validate method exists
                    if isinstance(node.func.value, ast.Attribute):
                        if isinstance(node.func.value.value, ast.Attribute):
                            if (isinstance(node.func.value.value.value, ast.Name) and
                                node.func.value.value.value.id == 'self' and
                                node.func.value.value.attr == 'services'):
                                
                                service_name = node.func.value.attr
                                method_name = node.func.attr
                                
                                # Check if service exists
                                if service_name in self.service_registry:
                                    # Check if method exists in service
                                    if method_name not in self.service_registry[service_name]:
                                        line_num = node.lineno if hasattr(node, 'lineno') else 0
                                        self.missing_services.append({
                                            'service_name': service_name,
                                            'method_name': method_name,
                                            'line': line_num,
                                            'type': 'method'
                                        })
                                        errors.append(f"Unknown method: self.services.{service_name}.{method_name}() (line {line_num})")
                    
                    # Check for direct self.service_method() that should be self.services.method()
                    if isinstance(node.func.value, ast.Name) and node.func.value.id == 'self':
                        method_name = node.func.attr
                        
                        # Check if this looks like a service method
                        if method_name in self.available_services:
                            return False, f"Method '{method.name}' calls 'self.{method_name}()' but should use 'self.services.{method_name}()'"
        
        if errors:
            return False, "CUA validation failed:\n  " + "\n  ".join(f"[HIGH] {e}" for e in errors)
        
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
