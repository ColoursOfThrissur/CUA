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
            'http': ['get', 'post', 'put', 'delete'],
            'fs': ['read', 'write', 'list'],
            'json': ['parse', 'stringify', 'query'],
            'shell': ['execute'],
            'time': ['now_utc', 'now_local', 'now_utc_iso', 'now_local_iso'],
            'ids': ['generate', 'uuid'],
            'logging': ['info', 'warning', 'error', 'debug'],
            'browser': ['open_browser', 'navigate', 'find_element', 'get_page_text', 'take_screenshot', 'close', 'is_available'],
            # Direct methods on ToolServices (self.services.<method>(...))
            'call_tool': [],
            'list_tools': [],
            'has_capability': [],
            'detect_language': [],
            'extract_key_points': [],
            'sentiment_analysis': [],
            'generate_json_output': [],
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
    
    # Modules that must never be imported in generated tool code
    _BLOCKED_IMPORTS = {"subprocess", "pty", "pexpect", "fabric", "paramiko"}
    # Dangerous attribute calls that bypass the shell allowlist
    _DANGEROUS_CALLS = {
        "os.system", "os.popen", "os.execv", "os.execve", "os.execle",
        "os.execlp", "os.execvp", "os.execvpe", "os.spawnl", "os.spawnle",
        "os.spawnlp", "os.spawnv", "os.spawnve", "os.spawnvp",
        "subprocess.run", "subprocess.call", "subprocess.Popen",
        "subprocess.check_output", "subprocess.check_call",
        # asyncio event loop blocking calls crash inside FastAPI's running loop
        "asyncio.get_event_loop", "loop.run_until_complete",
    }
    _DANGEROUS_BUILTINS = {"eval", "exec", "compile", "__import__"}

    def _check_dangerous_calls(self, code: str) -> Tuple[bool, str]:
        """Block dangerous imports and direct os/subprocess/eval usage."""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return True, ""  # syntax errors caught later

        for node in ast.walk(tree):
            # Block banned module imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root in self._BLOCKED_IMPORTS:
                        return False, (
                            f"Import of '{alias.name}' is not allowed in tool code — "
                            "use self.services.shell.execute() for shell commands"
                        )
            if isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                if root in self._BLOCKED_IMPORTS:
                    return False, (
                        f"Import from '{node.module}' is not allowed in tool code — "
                        "use self.services.shell.execute() for shell commands"
                    )

            if isinstance(node, ast.Call):
                func = node.func
                # eval / exec / compile / __import__
                if isinstance(func, ast.Name) and func.id in self._DANGEROUS_BUILTINS:
                    return False, f"Dangerous builtin '{func.id}()' not allowed in tool code"
                # os.system / subprocess.run / etc. via attribute access
                if isinstance(func, ast.Attribute):
                    full = f"{getattr(func.value, 'id', '')}.{func.attr}"
                    if full in self._DANGEROUS_CALLS:
                        return False, (
                            f"Dangerous call '{full}()' not allowed — "
                            "use self.services.shell.execute()"
                        )
                    # Also catch run_until_complete regardless of variable name
                    if func.attr == 'run_until_complete':
                        return False, (
                            "'run_until_complete()' not allowed in tool code — "
                            "use concurrent.futures.ThreadPoolExecutor for parallel execution"
                        )
        return True, ""

    def validate(self, code: str, class_name: Optional[str] = None) -> Tuple[bool, str]:
        """Run all enhanced validations."""

        # Reset missing services tracker
        self.missing_services = []

        # 0. Block dangerous system calls
        is_valid, error = self._check_dangerous_calls(code)
        if not is_valid:
            return False, error

        # 1. Check for hardcoded placeholder values
        is_valid, error = self._check_hardcoded_values(code)
        if not is_valid:
            return False, error

        # 2. Check for truncation
        is_complete, truncation_error = self._check_truncation(code)
        if not is_complete:
            return False, truncation_error
        
        # 3. Parse AST
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"Syntax error: {e}"

        # 4. Find target class
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
        
        # 4b. Check for bare undefined function calls (hallucinated helpers)
        is_valid, error = self._check_bare_undefined_calls(target_class, code)
        if not is_valid:
            return False, error

        # 4b. Check for bare function calls that aren't builtins or imported names
        is_valid, error = self._check_bare_function_calls(tree, target_class)
        if not is_valid:
            return False, error

        # 4c. Check for duplicate capability names
        is_valid, error = self._check_duplicate_capabilities(target_class)
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
    
    def _check_hardcoded_values(self, code: str) -> Tuple[bool, str]:
        """Check for hardcoded placeholder values that indicate stub/incomplete code."""
        patterns = [
            (r'example\.com', 'example.com - use parameters or config for URLs'),
            (r'test_user|test_password|testuser|testpass', 'test credentials - use parameters'),
            (r'api_key\s*=\s*["\'][^"\']', 'hardcoded API key - use environment variables'),
            (r'password\s*=\s*["\'][^"\']', 'hardcoded password - use parameters'),
            (r'https?://api\.example', 'api.example.com - use configurable endpoints'),
            (r'localhost:\d+', 'hardcoded localhost URL - use parameters'),
            (r'127\.0\.0\.1:\d+', 'hardcoded 127.0.0.1 - use parameters'),
        ]
        
        for pattern, description in patterns:
            matches = re.finditer(pattern, code, re.I)
            for match in matches:
                # Get line number
                line_num = code[:match.start()].count('\n') + 1
                return False, f"Hardcoded value detected (line {line_num}): {description}"
        
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
    
    def _check_bare_undefined_calls(self, target_class: ast.ClassDef, code: str) -> Tuple[bool, str]:
        """Detect bare function calls that are not builtins, imports, or class methods.

        Catches LLM hallucinations like output_validation(), validate_result(),
        format_response() that are neither defined in the class nor imported.
        """
        import builtins
        builtin_names = set(dir(builtins))
        # Collect names imported at module level
        try:
            tree = ast.parse(code)
        except Exception:
            return True, ""
        imported_names: set = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_names.add(alias.asname or alias.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    imported_names.add(alias.asname or alias.name)
        # Collect names defined at class level (methods + class vars)
        class_names: set = set()
        for node in target_class.body:
            if isinstance(node, ast.FunctionDef):
                class_names.add(node.name)
        # Walk each method looking for bare Name calls
        for method in target_class.body:
            if not isinstance(method, ast.FunctionDef):
                continue
            # Collect local names (params + assignments) in this method
            local_names: set = {arg.arg for arg in method.args.args}
            for node in ast.walk(method):
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    for t in targets:
                        if isinstance(t, ast.Name):
                            local_names.add(t.id)
                elif isinstance(node, ast.For):
                    if isinstance(node.target, ast.Name):
                        local_names.add(node.target.id)
                elif isinstance(node, (ast.With, ast.withitem)):
                    if isinstance(node, ast.With):
                        for item in node.items:
                            if item.optional_vars and isinstance(item.optional_vars, ast.Name):
                                local_names.add(item.optional_vars.id)
            for node in ast.walk(method):
                if not isinstance(node, ast.Call):
                    continue
                if not isinstance(node.func, ast.Name):
                    continue
                name = node.func.id
                if name in builtin_names or name in imported_names or name in local_names:
                    continue
                if name in class_names:  # defined as a method (called without self — unusual but valid)
                    continue
                return False, (
                    f"Method '{method.name}' calls undefined function '{name}()'. "
                    "Use self.services.X for operations or define the function in the class."
                )
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
    
    # Known safe bare-call names: builtins + common stdlib functions used in tools
    _SAFE_BARE_CALLS = {
        # builtins
        "print", "len", "range", "enumerate", "zip", "map", "filter", "sorted",
        "list", "dict", "set", "tuple", "str", "int", "float", "bool", "bytes",
        "isinstance", "issubclass", "hasattr", "getattr", "setattr", "delattr",
        "type", "repr", "hash", "id", "abs", "round", "min", "max", "sum",
        "any", "all", "next", "iter", "open", "vars", "dir", "callable",
        "super", "object", "property", "staticmethod", "classmethod",
        "Exception", "ValueError", "TypeError", "KeyError", "IndexError",
        "AttributeError", "RuntimeError", "NotImplementedError", "StopIteration",
        "IOError", "OSError", "FileNotFoundError", "PermissionError",
        # common patterns in tool code
        "datetime", "Path", "json", "re", "logging", "traceback",
    }

    def _check_bare_function_calls(self, tree: ast.Module, target_class: ast.ClassDef) -> Tuple[bool, str]:
        """Catch bare function calls that aren't builtins, imports, or class methods."""
        # Collect all names imported at module level
        imported_names: Set[str] = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_names.add(alias.asname or alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    imported_names.add(alias.asname or alias.name)

        # Collect class-level defined names (methods + class vars)
        class_names: Set[str] = set()
        for node in target_class.body:
            if isinstance(node, ast.FunctionDef):
                class_names.add(node.name)
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        class_names.add(t.id)

        safe = self._SAFE_BARE_CALLS | imported_names | class_names

        for method in target_class.body:
            if not isinstance(method, ast.FunctionDef):
                continue
            # Collect local names (args + assignments) within this method
            local_names: Set[str] = {arg.arg for arg in method.args.args}
            if method.args.vararg:
                local_names.add(method.args.vararg.arg)
            if method.args.kwarg:
                local_names.add(method.args.kwarg.arg)
            for node in ast.walk(method):
                if isinstance(node, ast.Assign):
                    for t in node.targets:
                        if isinstance(t, ast.Name):
                            local_names.add(t.id)
                elif isinstance(node, (ast.For, ast.comprehension)):
                    target = getattr(node, "target", None)
                    if target and isinstance(target, ast.Name):
                        local_names.add(target.id)

            all_safe = safe | local_names
            for node in ast.walk(method):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                # Only flag bare Name calls (not attribute calls like self.x() or obj.method())
                if isinstance(func, ast.Name) and func.id not in all_safe:
                    return False, (
                        f"Method '{method.name}' calls undefined bare function '{func.id}()'. "
                        "Use self.services.* for service calls or import the function."
                    )
        return True, ""

    def _check_duplicate_capabilities(self, target_class: ast.ClassDef) -> Tuple[bool, str]:
        """Detect duplicate capability names registered in register_capabilities."""
        register_method = next(
            (m for m in target_class.body
             if isinstance(m, ast.FunctionDef) and m.name == "register_capabilities"),
            None,
        )
        if not register_method:
            return True, ""

        seen: Dict[str, int] = {}
        for node in ast.walk(register_method):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == "add_capability"):
                continue
            # First positional arg or 'capability' keyword is the ToolCapability object.
            # The capability name is inside ToolCapability(name=...) — find it via the
            # variable assigned just before this call.
            # Simpler: walk for ToolCapability(name=...) calls and collect names.
        cap_names: List[str] = []
        for node in ast.walk(register_method):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name) and func.id == "ToolCapability":
                for kw in node.keywords:
                    if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                        cap_names.append(str(kw.value.value))
        duplicates = [n for n in cap_names if cap_names.count(n) > 1]
        if duplicates:
            return False, (
                f"Duplicate capability name(s) in register_capabilities: {sorted(set(duplicates))}. "
                "Remove the duplicate ToolCapability definition."
            )
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

                func = node.func
                if not isinstance(func, ast.Attribute):
                    continue

                # Pattern: self.services.<svc>.<method>(...)
                if (
                    isinstance(func.value, ast.Attribute)
                    and isinstance(func.value.value, ast.Attribute)
                    and isinstance(func.value.value.value, ast.Name)
                    and func.value.value.value.id == 'self'
                    and func.value.value.attr == 'services'
                ):
                    service_name = func.value.attr
                    method_name = func.attr
                    line_num = getattr(node, 'lineno', 0)

                    if service_name not in self.service_registry:
                        self.missing_services.append({'service_name': service_name, 'method_name': None, 'line': line_num, 'type': 'full_service'})
                        errors.append(f"Unknown service: self.services.{service_name} (line {line_num})")
                    else:
                        allowed = self.service_registry[service_name]
                        if allowed and method_name not in allowed:
                            self.missing_services.append({'service_name': service_name, 'method_name': method_name, 'line': line_num, 'type': 'method'})
                            errors.append(f"Unknown method: self.services.{service_name}.{method_name}() (line {line_num})")
                    continue

                # Pattern: self.services.<direct_method>(...)
                if (
                    isinstance(func.value, ast.Attribute)
                    and isinstance(func.value.value, ast.Name)
                    and func.value.value.id == 'self'
                    and func.value.attr == 'services'
                ):
                    # This is self.services.something() — only valid for direct methods
                    direct_name = func.attr
                    if direct_name in self.service_registry and self.service_registry[direct_name]:  # has sub-methods = nested service
                        line_num = getattr(node, 'lineno', 0)
                        errors.append(f"Invalid call self.services.{direct_name}(...) — use self.services.{direct_name}.<method>() (line {line_num})")
                    continue

                # Pattern: self.<method>() that should be self.services.<method>()
                if isinstance(func.value, ast.Name) and func.value.id == 'self':
                    method_name = func.attr
                    if method_name in self.available_services:
                        errors.append(f"Method '{method.name}' calls 'self.{method_name}()' but should use 'self.services.{method_name}()'")

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
