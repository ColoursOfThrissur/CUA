"""
Tool code validator - Comprehensive AST-based validation with service pattern validation
"""
import ast
import logging
from typing import Optional, Tuple, Dict, List, Set
from domain.services.architecture_contract import validate_architecture_contract
from infrastructure.validation.enhanced_code_validator import EnhancedCodeValidator
from infrastructure.external.service_validation import validate_tool_service_patterns
from domain.entities.skill_models import SkillDefinition

logger = logging.getLogger(__name__)


class ToolValidator:
    """Validates generated tool code against thin tool contracts"""
    
    def __init__(self):
        self.enhanced_validator = EnhancedCodeValidator()
        try:
            from infrastructure.analysis.cua_code_analyzer import CUACodeAnalyzer
            self._cua_analyzer = CUACodeAnalyzer()
        except Exception:
            self._cua_analyzer = None
    
    def validate(self, code: str, tool_spec: dict, skill_definition: Optional[SkillDefinition] = None) -> Tuple[bool, str]:
        """Validate generated tool code with comprehensive checks including service patterns"""
        contract_ok, contract_error = validate_architecture_contract(tool_spec or {})
        if not contract_ok:
            return False, self._format_error("Architecture contract", contract_error, code)

        expected_class = self._class_name(tool_spec['name'])
        
        # 0. Enhanced validation (truncation, undefined methods, uninitialized attrs)
        is_valid, error = self.enhanced_validator.validate(code, expected_class)
        if not is_valid:
            return False, self._format_error("Enhanced validation", error, code)

        # 0.4. CUA architecture analysis — block CRITICAL/HIGH issues
        if self._cua_analyzer:
            try:
                cua_issues = self._cua_analyzer.analyze(code, tool_spec)
                critical = [i for i in cua_issues if getattr(i, 'severity', '') in ('CRITICAL', 'HIGH')]
                if critical:
                    msgs = "; ".join(getattr(i, 'description', str(i)) for i in critical[:3])
                    return False, self._format_error("CUA analysis", msgs, code)
            except Exception:
                pass  # analyzer failure must never block creation
        
        # 0.5. Service pattern validation (NEW)
        if skill_definition:
            service_result = validate_tool_service_patterns(code, skill_definition)
            if not service_result.valid:
                error_msg = "; ".join(service_result.errors)
                return False, self._format_error("Service validation", error_msg, code)
            
            # Log warnings but don't fail validation
            if service_result.warnings:
                logger.warning(f"Service validation warnings: {'; '.join(service_result.warnings)}")
        
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, self._format_error("Syntax error", f"line {e.lineno}: {e.msg}", code, e.lineno)
        except Exception as e:
            return False, self._format_error("Parse error", str(e), code)
        
        target_class = self._find_class(tree, expected_class)
        if not target_class:
            return False, self._format_error("Class not found", f"Expected class '{expected_class}' not found", code)
        
        # Get all methods
        methods = {n.name: n for n in target_class.body if isinstance(n, ast.FunctionDef)}
        
        # Validate required methods exist
        register_method = methods.get("register_capabilities")
        if not register_method:
            return False, self._format_error("Missing method", "register_capabilities() missing", code)
        execute_method = methods.get("execute")
        if not execute_method:
            return False, self._format_error("Missing method", "execute() missing", code)
        
        # Validate execute signature
        error = self._validate_execute_signature(execute_method)
        if error:
            return False, self._format_error("Execute signature", error, code, execute_method.lineno)
        
        # Validate capabilities registration
        error = self._validate_capabilities_registration(register_method, target_class, methods)
        if error:
            return False, self._format_error("Capability registration", error, code, register_method.lineno)
        
        # Validate parameters and capabilities
        error = self._validate_parameters_and_capabilities(register_method)
        if error:
            return False, self._format_error("Parameter validation", error, code, register_method.lineno)
        
        # Validate __init__ accepts orchestrator
        init_method = methods.get("__init__")
        if init_method:
            init_params = [arg.arg for arg in init_method.args.args]
            if "orchestrator" not in init_params:
                return False, self._format_error("Init signature", "__init__ must accept 'orchestrator' parameter", code, init_method.lineno)
        
        # Validate no mutable default arguments
        error = self._validate_no_mutable_defaults(target_class)
        if error:
            return False, self._format_error("Mutable defaults", error, code)
        
        # Validate no ./ paths
        error = self._validate_no_relative_paths(target_class)
        if error:
            return False, self._format_error("Relative paths", error, code)
        
        # Validate no undefined helper calls
        error = self._validate_no_undefined_helpers(target_class)
        if error:
            return False, self._format_error("Undefined helpers", error, code)
        
        # Validate imports
        error = self._validate_imports(tree)
        if error:
            return False, self._format_error("Missing imports", error, code)
        
        # Validate isinstance usage
        error = self._validate_isinstance_usage(target_class)
        if error:
            return False, self._format_error("Isinstance usage", error, code)
        
        # Validate structural rules (execute delegation, return shape, call_tool usage)
        error = self._validate_structural_rules(target_class)
        if error:
            return False, self._format_error("Structural rules", error, code)
        
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
        # Dynamically get allowed parameter types from ParameterType enum
        from tools.tool_capability import ParameterType
        allowed_parameter_types = {pt.name for pt in ParameterType}
        
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
    
    def _validate_structural_rules(self, target_class: ast.ClassDef) -> Optional[str]:
        """Validate structural rules that the evolution pipeline depends on."""
        execute_method = next(
            (m for m in target_class.body if isinstance(m, ast.FunctionDef) and m.name == 'execute'), None
        )
        if execute_method:
            # Rule 1: execute() must delegate via execute_capability(), not manual if/elif
            has_execute_capability = False
            has_if_chain = False
            for node in ast.walk(execute_method):
                if isinstance(node, ast.Call):
                    func = node.func
                    if (isinstance(func, ast.Attribute) and func.attr == 'execute_capability'
                            and isinstance(func.value, ast.Name) and func.value.id == 'self'):
                        has_execute_capability = True
                if isinstance(node, ast.If):
                    # Check if it's comparing 'operation'
                    test = node.test
                    if isinstance(test, ast.Compare):
                        left = test.left
                        if isinstance(left, ast.Name) and left.id == 'operation':
                            has_if_chain = True
            if has_if_chain and not has_execute_capability:
                return ("execute() uses manual if/elif routing instead of "
                        "self.execute_capability(operation, **kwargs). "
                        "Remove the if/elif chain and use execute_capability() delegation.")

        # Rule 5: call_tool must not target private methods
        for method in target_class.body:
            if not isinstance(method, ast.FunctionDef):
                continue
            for node in ast.walk(method):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                # self.services.call_tool(...)
                if (isinstance(func, ast.Attribute) and func.attr == 'call_tool'
                        and isinstance(func.value, ast.Attribute)
                        and func.value.attr == 'services'):
                    # Third positional arg or 'operation' keyword is the operation name
                    op_arg = None
                    if len(node.args) >= 2:
                        op_arg = node.args[1]
                    else:
                        for kw in node.keywords:
                            if kw.arg == 'operation':
                                op_arg = kw.value
                                break
                    if op_arg and isinstance(op_arg, ast.Constant):
                        op_name = str(op_arg.value)
                        if op_name.startswith('_'):
                            return (f"call_tool() targets private method '{op_name}'. "
                                    "Only public capability names may be used with call_tool().")
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

    
    def _format_error(self, category: str, message: str, code: str, line_num: int = None) -> str:
        """Format validation error with code snippet and fix suggestion"""
        lines = code.split('\n')
        
        # Build error message
        parts = [f"[{category}] {message}"]
        
        # Add line number if available
        if line_num and 1 <= line_num <= len(lines):
            parts.append(f"\nLine {line_num}:")
            # Show 2 lines before and after for context
            start = max(0, line_num - 3)
            end = min(len(lines), line_num + 2)
            for i in range(start, end):
                prefix = ">>> " if i == line_num - 1 else "    "
                parts.append(f"{prefix}{i+1:4d} | {lines[i]}")
        
        # Add fix suggestion based on category
        fix = self._get_fix_suggestion(category, message)
        if fix:
            parts.append(f"\nFix: {fix}")
        
        return '\n'.join(parts)
    
    def _get_fix_suggestion(self, category: str, message: str) -> str:
        """Get fix suggestion based on error category"""
        suggestions = {
            "Missing method": "Add the required method to your class",
            "Execute signature": "Change execute signature to: def execute(self, operation: str, **kwargs)",
            "Init signature": "Change __init__ signature to: def __init__(self, orchestrator=None)",
            "Capability registration": "Use self.add_capability(capability, handler_method)",
            "Parameter validation": "Check Parameter() objects have required fields: name, type, description, required",
            "Missing imports": "Add missing import at top of file",
            "Mutable defaults": "Replace mutable default with None, then assign in method body",
            "Relative paths": "Use absolute paths like 'data/tool_name/' instead of './'",
            "Undefined helpers": "Define the helper method or remove the call",
            "Service validation": "Ensure tool uses appropriate self.services.X patterns for skill domain",
        }
        return suggestions.get(category, "Review the error and fix the code")
    
    def _class_name(self, tool_name: str) -> str:
        from infrastructure.code_generation.tool_creation.base import canonical_class_name
        return canonical_class_name(tool_name)
