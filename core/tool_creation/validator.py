"""
Tool code validator - Comprehensive AST-based validation
"""
import ast
import logging
from typing import Optional, Tuple, Dict, List, Set

logger = logging.getLogger(__name__)


class ToolValidator:
    """Validates generated tool code against thin tool contracts"""
    
    def validate(self, code: str, tool_spec: dict) -> Tuple[bool, str]:
        """Validate generated tool code with comprehensive checks"""
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"line {e.lineno}: {e.msg}"
        except Exception as e:
            return False, str(e)
        
        expected_class = self._class_name(tool_spec['name'])
        target_class = self._find_class(tree, expected_class)
        if not target_class:
            return False, f"Expected class '{expected_class}' not found"
        
        # Get all methods
        methods = {n.name: n for n in target_class.body if isinstance(n, ast.FunctionDef)}
        
        # Validate required methods exist
        register_method = methods.get("register_capabilities")
        if not register_method:
            return False, "register_capabilities() missing"
        execute_method = methods.get("execute")
        if not execute_method:
            return False, "execute() missing"
        
        # Validate execute signature
        error = self._validate_execute_signature(execute_method)
        if error:
            return False, error
        
        # Validate capabilities registration
        error = self._validate_capabilities_registration(register_method, target_class, methods)
        if error:
            return False, error
        
        # Validate parameters and capabilities
        error = self._validate_parameters_and_capabilities(register_method)
        if error:
            return False, error
        
        # Validate __init__ accepts orchestrator
        init_method = methods.get("__init__")
        if init_method:
            init_params = [arg.arg for arg in init_method.args.args]
            if "orchestrator" not in init_params:
                return False, "__init__ must accept 'orchestrator' parameter"
        
        # Validate no mutable default arguments
        error = self._validate_no_mutable_defaults(target_class)
        if error:
            return False, error
        
        # Validate no ./ paths
        error = self._validate_no_relative_paths(target_class)
        if error:
            return False, error
        
        # Validate no undefined helper calls
        error = self._validate_no_undefined_helpers(target_class)
        if error:
            return False, error
        
        # Validate imports
        error = self._validate_imports(tree)
        if error:
            return False, error
        
        # Validate isinstance usage
        error = self._validate_isinstance_usage(target_class)
        if error:
            return False, error
        
        return True, ""
    
    def _validate_execute_signature(self, execute_method: ast.FunctionDef) -> Optional[str]:
        """Validate execute method signature"""
        execute_params = [arg.arg for arg in execute_method.args.args]
        if len(execute_params) < 2 or execute_params[0] != "self" or execute_params[1] != "operation":
            return "execute() signature must start with (self, operation)"
        
        supports_parameters_dict = len(execute_params) >= 3 and execute_params[2] == "parameters"
        has_kwargs = execute_method.args.kwarg is not None
        if not supports_parameters_dict and not has_kwargs:
            return "execute() must accept parameters dict or **kwargs"
        
        return None
    
    def _validate_capabilities_registration(
        self, 
        register_method: ast.FunctionDef, 
        target_class: ast.ClassDef,
        methods: Dict[str, ast.FunctionDef]
    ) -> Optional[str]:
        """Validate capabilities registration logic"""
        class_method_names = {m.name for m in target_class.body if isinstance(m, ast.FunctionDef)}
        
        has_add_capability = False
        bad_add_capability_signature = False
        invalid_add_capability_keyword = False
        missing_handler_method = None
        
        for node in ast.walk(register_method):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "self":
                    if node.func.attr == "add_capability":
                        has_add_capability = True
                        
                        # Check keyword arguments
                        if node.keywords:
                            keyword_names = {k.arg for k in node.keywords if k.arg}
                            if "handler" in keyword_names:
                                invalid_add_capability_keyword = True
                            if not ({"capability", "handler_func"} <= keyword_names):
                                bad_add_capability_signature = True
                            
                            # Check handler method exists
                            for kw in node.keywords:
                                if kw.arg == "handler_func" and isinstance(kw.value, ast.Attribute):
                                    if isinstance(kw.value.value, ast.Name) and kw.value.value.id == "self":
                                        if kw.value.attr not in class_method_names:
                                            missing_handler_method = kw.value.attr
                        
                        # Check positional arguments
                        elif len(node.args) < 2:
                            bad_add_capability_signature = True
                        else:
                            handler = node.args[1]
                            if isinstance(handler, ast.Attribute):
                                if isinstance(handler.value, ast.Name) and handler.value.id == "self":
                                    if handler.attr not in class_method_names:
                                        missing_handler_method = handler.attr
            
            # Check for direct self.capabilities assignment (disallowed)
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Attribute):
                        if isinstance(target.value, ast.Name) and target.value.id == "self" and target.attr == "capabilities":
                            return "register_capabilities() must not assign self.capabilities directly"
        
        if not has_add_capability:
            return "register_capabilities() must call self.add_capability(...)"
        if invalid_add_capability_keyword:
            return "self.add_capability(...) must use handler_func keyword, not handler"
        if bad_add_capability_signature:
            return "self.add_capability(...) must include capability and handler"
        if missing_handler_method:
            return f"add_capability handler method '{missing_handler_method}' not found in class"
        
        return None
    
    def _validate_parameters_and_capabilities(self, register_method: ast.FunctionDef) -> Optional[str]:
        """Validate Parameter and ToolCapability objects"""
        allowed_parameter_types = {"STRING", "INTEGER", "BOOLEAN", "LIST", "DICT", "FILE_PATH"}
        
        for node in ast.walk(register_method):
            if not isinstance(node, ast.Call):
                continue
            
            # Validate Parameter objects
            if isinstance(node.func, ast.Name) and node.func.id == "Parameter":
                keyword_names = {k.arg for k in node.keywords if k.arg}
                
                if "description" not in keyword_names:
                    return "Parameter(...) must include description=..."
                
                if "optional" in keyword_names:
                    return "Parameter(...) must use required=..., not optional=..."
                
                # Check required=True with default set
                if "required" in keyword_names and "default" in keyword_names:
                    required_kw = next((k for k in node.keywords if k.arg == "required"), None)
                    default_kw = next((k for k in node.keywords if k.arg == "default"), None)
                    if (isinstance(required_kw.value, ast.Constant) and 
                        required_kw.value.value is True and
                        isinstance(default_kw.value, ast.Constant) and 
                        default_kw.value.value is not None):
                        return "Parameter(...) cannot be required=True when default is set"
                
                # Validate ParameterType
                for kw in node.keywords:
                    if kw.arg == "type" and isinstance(kw.value, ast.Attribute):
                        if isinstance(kw.value.value, ast.Name) and kw.value.value.id == "ParameterType":
                            if kw.value.attr not in allowed_parameter_types:
                                return f"Unsupported ParameterType.{kw.value.attr}"
            
            # Validate ToolCapability objects
            if isinstance(node.func, ast.Name) and node.func.id == "ToolCapability":
                keyword_names = {k.arg for k in node.keywords if k.arg}
                required = {"name", "description", "parameters", "returns", "safety_level", "examples"}
                
                if "operation" in keyword_names:
                    return "ToolCapability(...) must use name=..., not operation=..."
                
                if node.keywords and not required.issubset(keyword_names):
                    return "ToolCapability(...) missing required fields"
                
                # Validate returns is a string
                for kw in node.keywords:
                    if kw.arg == "returns":
                        if not (isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str)):
                            return "ToolCapability(..., returns=...) must be a string description"
        
        return None
    
    def _validate_no_mutable_defaults(self, target_class: ast.ClassDef) -> Optional[str]:
        """Validate no mutable default arguments"""
        for node in ast.walk(target_class):
            if not isinstance(node, ast.FunctionDef):
                continue
            
            defaults = list(node.args.defaults) + [d for d in node.args.kw_defaults if d is not None]
            for default in defaults:
                if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                    return f"Function '{node.name}' uses mutable default argument"
                if isinstance(default, ast.Call) and isinstance(default.func, ast.Name):
                    if default.func.id in {"list", "dict", "set"}:
                        return f"Function '{node.name}' uses mutable default argument"
        
        return None
    
    def _validate_no_relative_paths(self, target_class: ast.ClassDef) -> Optional[str]:
        """Validate no ./ relative paths"""
        for method in target_class.body:
            if not isinstance(method, ast.FunctionDef):
                continue
            
            for node in ast.walk(method):
                if not isinstance(node, ast.Assign):
                    continue
                
                for target in node.targets:
                    if not isinstance(target, ast.Attribute):
                        continue
                    if not isinstance(target.value, ast.Name) or target.value.id != "self":
                        continue
                    if not isinstance(node.value, ast.Constant) or not isinstance(node.value.value, str):
                        continue
                    
                    attr_name = target.attr.lower()
                    value = node.value.value.strip()
                    if (attr_name.endswith("_dir") or "path" in attr_name) and value.startswith("./"):
                        return "Use deterministic data/ paths instead of './' paths"
        
        return None
    
    def _validate_no_undefined_helpers(self, target_class: ast.ClassDef) -> Optional[str]:
        """Validate no calls to undefined private helper methods"""
        class_methods = {m.name for m in target_class.body if isinstance(m, ast.FunctionDef)}
        
        for method in [m for m in target_class.body if isinstance(m, ast.FunctionDef)]:
            for node in ast.walk(method):
                if not isinstance(node, ast.Call):
                    continue
                if not isinstance(node.func, ast.Attribute):
                    continue
                if not isinstance(node.func.value, ast.Name) or node.func.value.id != "self":
                    continue
                
                called = node.func.attr
                if not called.startswith("_") or called.startswith("__"):
                    continue
                if called in class_methods:
                    continue
                
                return f"Method '{method.name}' calls undefined helper '{called}'"
        
        return None
    
    def _validate_imports(self, tree: ast.Module) -> Optional[str]:
        """Validate required symbols are imported"""
        imported = set()
        assigned = set()
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.asname or alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    imported.add(alias.asname or alias.name)
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        assigned.add(t.id)
            elif isinstance(node, ast.FunctionDef):
                for arg in node.args.args:
                    assigned.add(arg.arg)
                if node.args.kwarg:
                    assigned.add(node.args.kwarg.arg)
        
        required_symbols = {"Path", "json"}
        used = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                if node.id in required_symbols:
                    used.add(node.id)
        
        for sym in sorted(used):
            if sym not in imported and sym not in assigned:
                return f"Symbol '{sym}' is used but not imported"
        
        return None
    
    def _validate_isinstance_usage(self, target_class: ast.ClassDef) -> Optional[str]:
        """Validate isinstance doesn't use ParameterType enums"""
        for method in [m for m in target_class.body if isinstance(m, ast.FunctionDef)]:
            for node in ast.walk(method):
                if not isinstance(node, ast.Call):
                    continue
                if not (isinstance(node.func, ast.Name) and node.func.id == "isinstance"):
                    continue
                if len(node.args) < 2:
                    continue
                
                second = node.args[1]
                if (isinstance(second, ast.Attribute) and 
                    isinstance(second.value, ast.Name) and 
                    second.value.id == "ParameterType"):
                    return (f"Method '{method.name}' uses isinstance(..., ParameterType.{second.attr}); "
                           "use concrete Python types (str, int, bool, list, dict) instead")
        
        return None
    
    def _find_class(self, tree: ast.Module, class_name: str) -> Optional[ast.ClassDef]:
        """Find class by name in AST"""
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                return node
        return None

    
    def _class_name(self, tool_name: str) -> str:
        """Convert tool_name to ClassName"""
        return ''.join((part[:1].upper() + part[1:]) for part in tool_name.split('_') if part)
