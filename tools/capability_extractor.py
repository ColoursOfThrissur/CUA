"""
Deterministic Capability Extractor - AST-based extraction from ToolCapability metadata
"""
import ast
from typing import Dict, List, Optional
from pathlib import Path

class CapabilityExtractor:
    """Extract capabilities from tool files using AST parsing of register_capabilities()"""
    
    def extract_from_file(self, file_path: str) -> Optional[Dict]:
        """Extract capabilities from tool file"""
        try:
            code = Path(file_path).read_text(encoding='utf-8')
            tree = ast.parse(code)
            
            # Find class definition
            class_node = self._find_class(tree)
            if not class_node:
                raise ValueError(f"No class definition found in {file_path}")
            
            # Extract class docstring
            description = ast.get_docstring(class_node) or ""
            
            # Find register_capabilities method
            register_method = self._find_register_capabilities(class_node)
            if not register_method:
                raise ValueError(f"Missing register_capabilities() in {class_node.name}. All tools must implement this method.")
            
            # Extract ToolCapability instantiations
            capabilities = self._extract_capabilities(register_method)
            
            if not capabilities:
                raise ValueError(f"No ToolCapability definitions found in register_capabilities() for {class_node.name}")
            
            # Validate handlers exist
            self._validate_handlers(class_node, capabilities)
            
            # Extract version if present
            version = self._extract_version(class_node)
            
            return {
                "name": class_node.name,
                "version": version,
                "description": description.split('\n')[0] if description else "",
                "operations": capabilities
            }
            
        except Exception as e:
            raise ValueError(f"Capability extraction failed for {file_path}: {e}")
    
    def _find_class(self, tree: ast.Module) -> Optional[ast.ClassDef]:
        """Find the most likely tool class (prefer BaseTool subclasses)."""
        candidates: List[ast.ClassDef] = [n for n in tree.body if isinstance(n, ast.ClassDef)]
        if not candidates:
            return None

        def _is_basetool_subclass(cls: ast.ClassDef) -> bool:
            for base in cls.bases:
                if isinstance(base, ast.Name) and base.id == "BaseTool":
                    return True
                if isinstance(base, ast.Attribute) and base.attr == "BaseTool":
                    return True
            return False

        for cls in candidates:
            if _is_basetool_subclass(cls):
                return cls
        # Fallback to first class for backward compatibility.
        return candidates[0]
    
    def _find_register_capabilities(self, class_node: ast.ClassDef) -> Optional[ast.FunctionDef]:
        """Find register_capabilities method"""
        for node in class_node.body:
            if isinstance(node, ast.FunctionDef) and node.name == 'register_capabilities':
                return node
        return None
    
    def _extract_capabilities(self, method: ast.FunctionDef) -> Dict:
        """Extract ToolCapability instantiations from method"""
        capabilities = {}
        
        for node in ast.walk(method):
            # Look for ToolCapability(...) calls
            if isinstance(node, ast.Call):
                if self._is_tool_capability_call(node):
                    cap = self._parse_capability(node)
                    if cap:
                        capabilities[cap['name']] = {
                            'parameters': cap['parameters'],
                            'required': cap['required'],
                            'description': cap['description'],
                            'safety_level': cap.get('safety_level')
                        }
                # Also look for self.add_capability(cap, handler) pattern
                elif self._is_add_capability_call(node):
                    if node.args and isinstance(node.args[0], ast.Name):
                        # Find the variable assignment
                        var_name = node.args[0].id
                        cap = self._find_capability_var(method, var_name)
                        if cap:
                            capabilities[cap['name']] = {
                                'parameters': cap['parameters'],
                                'required': cap['required'],
                                'description': cap['description'],
                                'safety_level': cap.get('safety_level')
                            }
        
        return capabilities
    
    def _is_add_capability_call(self, node: ast.Call) -> bool:
        """Check if node is self.add_capability(...) call"""
        if isinstance(node.func, ast.Attribute):
            return node.func.attr == 'add_capability'
        return False
    
    def _find_capability_var(self, method: ast.FunctionDef, var_name: str) -> Optional[Dict]:
        """Find ToolCapability assigned to variable"""
        for node in ast.walk(method):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == var_name:
                        if isinstance(node.value, ast.Call) and self._is_tool_capability_call(node.value):
                            return self._parse_capability(node.value)
        return None
    
    def _is_tool_capability_call(self, node: ast.Call) -> bool:
        """Check if node is ToolCapability(...) call"""
        if isinstance(node.func, ast.Name):
            return node.func.id == 'ToolCapability'
        return False
    
    def _parse_capability(self, node: ast.Call) -> Optional[Dict]:
        """Parse ToolCapability instantiation"""
        cap = {
            'name': None,
            'description': '',
            'parameters': [],
            'required': [],
            'safety_level': None
        }
        
        # Parse keyword arguments
        for keyword in node.keywords:
            if keyword.arg == 'name':
                cap['name'] = self._get_string_value(keyword.value)
            elif keyword.arg == 'description':
                cap['description'] = self._get_string_value(keyword.value)
            elif keyword.arg == 'parameters':
                cap['parameters'], cap['required'] = self._parse_parameters(keyword.value)
            elif keyword.arg == 'safety_level':
                cap['safety_level'] = self._get_attr_value(keyword.value)
        
        return cap if cap['name'] else None
    
    def _parse_parameters(self, node: ast.expr) -> tuple:
        """Parse parameters list and extract required flags"""
        params = []
        required = []
        
        if isinstance(node, ast.List):
            for elem in node.elts:
                if isinstance(elem, ast.Call) and isinstance(elem.func, ast.Name):
                    if elem.func.id == 'Parameter':
                        param_name = None
                        is_required = True  # Default
                        
                        # First positional arg is name
                        if elem.args:
                            param_name = self._get_string_value(elem.args[0])
                        
                        # Also support keyword-style name=...
                        for kw in elem.keywords:
                            if kw.arg == 'name' and not param_name:
                                param_name = self._get_string_value(kw.value)
                        
                        # Check for required keyword
                        for kw in elem.keywords:
                            if kw.arg == 'required':
                                is_required = self._get_bool_value(kw.value)
                        
                        if param_name:
                            params.append(param_name)
                            if is_required:
                                required.append(param_name)
        
        return params, required
    
    def _get_string_value(self, node: ast.expr) -> str:
        """Extract string value from AST node"""
        if isinstance(node, ast.Constant):
            return str(node.value)
        elif isinstance(node, ast.Str):  # Python 3.7 compatibility
            return node.s
        return ""
    
    def _get_bool_value(self, node: ast.expr) -> bool:
        """Extract boolean value from AST node"""
        if isinstance(node, ast.Constant):
            return bool(node.value)
        elif isinstance(node, ast.NameConstant):  # Python 3.7
            return bool(node.value)
        return True
    
    def _get_attr_value(self, node: ast.expr) -> Optional[str]:
        """Extract attribute value like SafetyLevel.LOW"""
        if isinstance(node, ast.Attribute):
            return node.attr
        return None
    
    def _extract_version(self, class_node: ast.ClassDef) -> Optional[str]:
        """Extract version attribute if present"""
        for node in class_node.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == 'version':
                        return self._get_string_value(node.value)
        return None
    
    def _validate_handlers(self, class_node: ast.ClassDef, capabilities: Dict):
        """Validate that handlers exist for all capabilities"""
        methods = {node.name for node in class_node.body if isinstance(node, ast.FunctionDef)}
        register_method = self._find_register_capabilities(class_node)

        for cap_name in capabilities.keys():
            handler_patterns = [f"_handle_{cap_name}", f"_{cap_name}", cap_name]
            has_named_handler = any(pattern in methods for pattern in handler_patterns)
            has_bound_handler = self._has_bound_handler(register_method, cap_name, methods) if register_method else False
            if not has_named_handler and not has_bound_handler:
                import warnings
                warnings.warn(f"Capability '{cap_name}' has no handler")

    def _has_bound_handler(self, register_method: ast.FunctionDef, cap_name: str, methods: set) -> bool:
        """Check if add_capability binds this capability to an existing class method."""
        for node in ast.walk(register_method):
            if not (isinstance(node, ast.Call) and self._is_add_capability_call(node)):
                continue
            capability_name = self._resolve_capability_name_arg(register_method, node)
            if capability_name != cap_name:
                continue
            handler_name = self._resolve_handler_name_arg(node)
            if handler_name and handler_name in methods:
                return True
        return False

    def _resolve_capability_name_arg(self, register_method: ast.FunctionDef, call: ast.Call) -> Optional[str]:
        """Resolve capability name passed to add_capability (var or direct call)."""
        # add_capability(ToolCapability(...), handler)
        if call.args:
            first = call.args[0]
            if isinstance(first, ast.Call) and self._is_tool_capability_call(first):
                parsed = self._parse_capability(first)
                return parsed.get("name") if parsed else None
            if isinstance(first, ast.Name):
                parsed = self._find_capability_var(register_method, first.id)
                return parsed.get("name") if parsed else None
        # add_capability(capability=...)
        for kw in call.keywords:
            if kw.arg == "capability":
                if isinstance(kw.value, ast.Call) and self._is_tool_capability_call(kw.value):
                    parsed = self._parse_capability(kw.value)
                    return parsed.get("name") if parsed else None
                if isinstance(kw.value, ast.Name):
                    parsed = self._find_capability_var(register_method, kw.value.id)
                    return parsed.get("name") if parsed else None
        return None

    def _resolve_handler_name_arg(self, call: ast.Call) -> Optional[str]:
        """Resolve bound handler method name from add_capability call."""
        if len(call.args) >= 2 and isinstance(call.args[1], ast.Attribute):
            attr = call.args[1]
            if isinstance(attr.value, ast.Name) and attr.value.id == "self":
                return attr.attr
        for kw in call.keywords:
            if kw.arg in {"handler_func", "handler"} and isinstance(kw.value, ast.Attribute):
                attr = kw.value
                if isinstance(attr.value, ast.Name) and attr.value.id == "self":
                    return attr.attr
        return None
