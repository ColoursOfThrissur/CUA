"""Qwen-style evolution code generator - preserves structure, improves handlers."""
import ast
import re
import textwrap
from typing import Dict, Any, Optional, List
from infrastructure.persistence.sqlite.logging import get_logger
from infrastructure.validation.enhanced_code_validator import EnhancedCodeValidator

logger = get_logger("code_generator")


class EvolutionCodeGenerator:
    """Generates improved tool code using multi-stage approach."""
    
    def __init__(self, llm_client):
        self.llm = llm_client
    
    def generate_improved_code(
        self, 
        current_code: str, 
        proposal: Dict[str, Any],
        sandbox_error: Optional[str] = None,
        validation_error: Optional[str] = None
    ) -> Optional[str]:
        """Generate improved code preserving structure.
        
        Args:
            current_code: The current tool code
            proposal: The improvement proposal
            sandbox_error: Error from previous sandbox failure (for retry feedback)
            validation_error: Error from previous validation failure (for retry feedback)
        """
        
        action_type = proposal.get('action_type', 'improve_logic')
        
        # For add_capability, create new handler + register capability
        if action_type == 'add_capability':
            return self._add_new_capability(current_code, proposal, sandbox_error, validation_error)
        
        # For fix_bug/improve_logic/refactor, modify existing handlers
        return self._improve_existing_handlers(current_code, proposal, sandbox_error, validation_error)
    
    def _extract_service_signatures(self) -> Dict[str, str]:
        """Extract actual method signatures from service classes using introspection."""
        import inspect
        signatures = {}
        
        try:
            from infrastructure.services.tool_services import BrowserService, StorageService, HTTPService
            
            # Dynamically extract browser service methods
            browser_methods = [
                m for m in dir(BrowserService)
                if not m.startswith('_') and callable(getattr(BrowserService, m, None))
            ]
            browser_sig = ", ".join([f"{m}(...)" for m in sorted(browser_methods)])
            signatures["browser"] = browser_sig if browser_sig else "open_browser(), navigate(url), find_element(by, value), get_page_text(), take_screenshot(filename), close(), is_available()"
            
            logger.debug(f"Extracted browser methods: {browser_sig}")
        except Exception as e:
            logger.warning(f"Could not extract browser service signatures: {e}")
        
        return signatures
    
    def _build_service_context(self) -> str:
        """Build grounded service context from actual service classes + fallback defaults."""
        registry = EnhancedCodeValidator().service_registry
        
        # Try to extract actual signatures first
        extracted = self._extract_service_signatures()
        
        # Fallback defaults if extraction fails
        nested = {
            "storage": "save(id, data), get(id), list(limit=10), find(filter_fn=None, limit=100), count(), update(id, updates), delete(id), exists(id)",
            "llm": "generate(prompt, temperature=0.3, max_tokens=500)",
            "http": "get(url), post(url, data), put(url, data), delete(url)",
            "fs": "read(path), write(path, content), list(path), exists(path), delete(path), mkdir(path)",
            "json": "parse(text), stringify(data, indent=None), query(data, path)",
            "shell": "execute(command)",
            "logging": "info(message), warning(message), error(message), debug(message)",
            "time": "now_utc(), now_local(), now_utc_iso(), now_local_iso()",
            "ids": "generate(prefix=\"\"), uuid()",
            "browser": "open_browser(), navigate(url), find_element(by, value), get_page_text(), take_screenshot(filename), close(), is_available()",
        }
        
        # Override with extracted signatures if available
        nested.update(extracted)
        direct = {
            "call_tool": "call_tool(tool_name, operation, **parameters)",
            "list_tools": "list_tools()",
            "has_capability": "has_capability(capability_name)",
            "detect_language": "detect_language(text)",
            "extract_key_points": "extract_key_points(text, style=\"bullet\", language=\"en\")",
            "sentiment_analysis": "sentiment_analysis(text, language=\"en\")",
            "generate_json_output": "generate_json_output(**kwargs)",
        }

        lines: List[str] = []
        for name in nested:
            if name in registry:
                lines.append(f"- self.services.{name}: {nested[name]}")
        for name in direct:
            if name in registry:
                lines.append(f"- self.services.{direct[name]}")

        lines.append("IMPORTANT: Do not call any self.services.* API not listed above.")
        lines.append("IMPORTANT: Do NOT import optional visualization libraries (graphviz, matplotlib, plotly, etc). Use self.services.json or self.services.storage for data output instead.")
        return "\n".join(lines)

    def _invalid_service_calls(self, code: str) -> List[str]:
        """Detect self.services calls that violate the service registry allowlist.

        Also catches extra arguments on methods with fixed signatures.
        Root cause of 'StorageService.get() got unexpected keyword argument default':
        LLM adds Python-idiom defaults (storage.get(id, default=None)) that don't
        exist on the actual service class. Method name check alone isn't enough.
        """
        registry = EnhancedCodeValidator().service_registry
        nested_allow = {k: set(v or []) for k, v in registry.items() if isinstance(v, list)}
        direct_allow = {k for k, v in registry.items() if isinstance(v, list) and len(v or []) == 0}

        # Methods that take exactly one positional arg (besides self)
        # Any extra args or kwargs are invalid
        SINGLE_ARG_METHODS = {
            ('storage', 'get'), ('storage', 'delete'), ('storage', 'exists'),
            ('storage', 'save'),  # save(id, data) -- 2 args, no kwargs
            ('llm', 'generate'),  # generate(prompt, temperature, max_tokens) -- no extra kwargs
            ('fs', 'read'), ('fs', 'delete'), ('fs', 'mkdir'),
            ('json', 'parse'), ('json', 'stringify'),
            ('shell', 'execute'),
        }

        invalid: List[str] = []

        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func

                # Correct pattern: self.services.<svc>.<method>
                # func.value = self.services.<svc>  (Attribute)
                # func.value.value = self.services  (Attribute)
                # func.value.value.value = self     (Name)
                if (isinstance(func, ast.Attribute)
                        and isinstance(func.value, ast.Attribute)
                        and isinstance(func.value.value, ast.Attribute)
                        and isinstance(func.value.value.value, ast.Name)
                        and func.value.value.value.id == 'self'
                        and func.value.value.attr == 'services'):
                    svc_name = func.value.attr
                    method_name = func.attr
                    # Check for unexpected keyword arguments on known fixed-signature methods
                    if (svc_name, method_name) in SINGLE_ARG_METHODS and node.keywords:
                        kw_names = [kw.arg for kw in node.keywords if kw.arg]
                        invalid.append(
                            f"self.services.{svc_name}.{method_name}() called with unexpected "
                            f"keyword argument(s): {kw_names}. "
                            f"Signature is {svc_name}.{method_name}() with no keyword args."
                        )
        except Exception:
            pass

        # Regex-based checks (method name allowlist)
        for svc, method in re.findall(r"self\.services\.(\w+)\.(\w+)\(", code):
            if svc not in nested_allow:
                invalid.append(f"Unknown service self.services.{svc}")
                continue
            allowed = nested_allow.get(svc, set())
            if allowed and method not in allowed:
                invalid.append(f"Unknown method self.services.{svc}.{method}")

        for name in re.findall(r"self\.services\.(\w+)\(", code):
            if name in nested_allow and (nested_allow.get(name) and name not in direct_allow):
                continue
            if name not in direct_allow:
                if name in nested_allow and name not in direct_allow:
                    invalid.append(f"Invalid call self.services.{name}(...) (service requires method like .save/.get)")
                else:
                    invalid.append(f"Unknown ToolServices method self.services.{name}")

        seen = set()
        out = []
        for item in invalid:
            if item not in seen:
                seen.add(item)
                out.append(item)
        return out
    
    def _improve_existing_handlers(
        self,
        current_code: str,
        proposal: Dict[str, Any],
        sandbox_error: Optional[str] = None,
        validation_error: Optional[str] = None
    ) -> Optional[str]:
        """Improve existing handlers (fix_bug/improve_logic/refactor).

        - Scopes to target_functions when specified.
        - Complexity guard: if >COMPLEXITY_THRESHOLD handlers and no target specified,
          skip rather than attempt a full rewrite of a large tool.
        - Passes the evolving file state forward so each handler sees what the
          previous handler produced.
        """
        from infrastructure.code_generation.tool_creation.base import COMPLEXITY_THRESHOLD

        class_name = self._extract_class_name(current_code)
        if not class_name:
            return None

        service_context = self._build_service_context()
        new_services_context = self._build_new_services_context(proposal)
        full_service_context = service_context + new_services_context

        all_handlers = self._extract_handlers(current_code, class_name)
        if not all_handlers:
            logger.warning("No handlers found to improve")
            return current_code

        target = proposal.get("target_functions") or []
        if target:
            handlers_to_improve = {k: v for k, v in all_handlers.items() if k in target}
            if not handlers_to_improve:
                logger.warning(f"target_functions {target} not found in handlers {list(all_handlers)}, falling back to all")
                handlers_to_improve = all_handlers
        else:
            # No target specified
            if len(all_handlers) > COMPLEXITY_THRESHOLD:
                logger.warning(
                    f"No target_functions specified and tool has {len(all_handlers)} handlers "
                    f"(>{COMPLEXITY_THRESHOLD}). Skipping full rewrite to avoid empty-code failure."
                )
                return current_code
            handlers_to_improve = all_handlers

        # Build tool purpose for context
        analysis = proposal.get("analysis") or {}
        tool_purpose = (
            proposal.get("description", "")
            + (f" | {analysis.get('summary', '')}" if analysis.get("summary") else "")
        )
        skill_name = ""
        verification_mode = ""
        exec_ctx = analysis.get("execution_context_data") or {}
        if isinstance(exec_ctx, dict):
            skill_name = exec_ctx.get("skill_name") or ""
            verification_mode = exec_ctx.get("verification_mode") or ""

        class_context = self._build_class_context(current_code, class_name)

        # Evolve handlers one at a time, passing the growing file forward
        improved_code = current_code
        already_improved: List[str] = []  # accumulates like creation pipeline
        for handler_name, handler_code in handlers_to_improve.items():
            logger.info(f"Improving handler: {handler_name}")
            improved_handler = self._improve_single_handler(
                handler_code=handler_code,
                handler_name=handler_name,
                proposal=proposal,
                class_name=class_name,
                service_context=full_service_context,
                sandbox_error=sandbox_error,
                validation_error=validation_error,
                class_context=class_context,
                tool_purpose=tool_purpose,
                skill_name=skill_name,
                verification_mode=verification_mode,
                current_file=improved_code,
                already_implemented=already_improved,
            )
            if improved_handler:
                improved_code = self._replace_handler(improved_code, handler_name, improved_handler, class_name)
                already_improved.append(handler_name)  # tell next handler what's done
                # Refresh class_context so next handler sees updated file
                class_context = self._build_class_context(improved_code, class_name)

        return improved_code
    
    def _add_new_capability(
        self,
        current_code: str,
        proposal: Dict[str, Any],
        sandbox_error: Optional[str] = None,
        validation_error: Optional[str] = None
    ) -> Optional[str]:
        """Add new capability (new handler + register in capabilities)."""
        class_name = self._extract_class_name(current_code)
        if not class_name:
            logger.error("Cannot add capability: no class name found")
            return None
        
        service_context = self._build_service_context()
        new_services_context = self._build_new_services_context(proposal)
        
        # Build existing capabilities summary so LLM doesn't duplicate them
        existing_caps = self._extract_tool_structure(current_code)

        # Build tool purpose from proposal + analysis
        analysis = proposal.get("analysis") or {}
        tool_purpose = (
            proposal.get("description", "")
            + (f" | {analysis.get('summary', '')}" if analysis.get("summary") else "")
        )
        exec_ctx = analysis.get("execution_context_data") or {}
        skill_name = exec_ctx.get("skill_name", "") if isinstance(exec_ctx, dict) else ""
        verification_mode = exec_ctx.get("verification_mode", "") if isinstance(exec_ctx, dict) else ""

        # Generate new handler
        new_handler = self._generate_new_handler(
            proposal,
            service_context + new_services_context,
            sandbox_error,
            validation_error,
            existing_capabilities=existing_caps,
            current_file=current_code,
            tool_purpose=tool_purpose,
            skill_name=skill_name,
            verification_mode=verification_mode,
        )
        if not new_handler:
            logger.error("Cannot add capability: handler generation failed")
            return None
        
        # Insert handler before execute() method
        improved_code = self._insert_handler_before_execute(current_code, new_handler, class_name)
        if not improved_code or len(improved_code) <= len(current_code):
            logger.error("Cannot add capability: handler insertion failed")
            return None
        
        # Update register_capabilities to include new operation
        improved_code = self._add_capability_registration(improved_code, proposal, class_name)
        if not improved_code or len(improved_code) <= len(current_code):
            logger.error("Cannot add capability: capability registration failed")
            return None
        
        # Update execute() method to route to new handler
        improved_code = self._add_execute_routing(improved_code, proposal, class_name)
        if not improved_code or len(improved_code) <= len(current_code):
            logger.error("Cannot add capability: execute routing failed")
            return None
        
        return improved_code
    
    def _build_new_services_context(self, proposal: Dict[str, Any]) -> str:
        """Build context for new services."""
        new_service_specs = proposal.get('new_service_specs') or {}
        if not new_service_specs:
            return ""
        
        context = "\n\nNEW SERVICES TO BE CREATED:\n"
        for svc_name, svc_spec in new_service_specs.items():
            context += f"- self.services.{svc_name}: {svc_spec['description']}\n"
            methods = svc_spec.get('methods', [])
            methods_str = ', '.join(str(m) for m in methods)
            context += f"  Methods: {methods_str}\n"
        return context
    
    def _generate_new_handler(
        self,
        proposal: Dict[str, Any],
        service_context: str,
        sandbox_error: Optional[str] = None,
        validation_error: Optional[str] = None,
        existing_capabilities: str = "",
        current_file: str = "",
        tool_purpose: str = "",
        skill_name: str = "",
        verification_mode: str = "",
    ) -> Optional[str]:
        """Generate new handler method for add_capability."""
        from infrastructure.code_generation.tool_creation.base import build_handler_context

        error_context = ""
        if validation_error:
            error_context = f"\n\nPREVIOUS ATTEMPT FAILED VALIDATION:\n{validation_error}\nFIX THESE ERRORS:\n"
        elif sandbox_error:
            error_context = f"\n\nPREVIOUS ATTEMPT FAILED:\n{sandbox_error}\n"

        operation_name = self._extract_operation_name(proposal)
        expected_name = f"_handle_{operation_name}"

        # Build op_spec from proposal changes so context builder has param info
        op_spec: Dict[str, Any] = {
            "parameters": [],
            "returns": "dict",
        }
        # Try to extract param names from changes text
        for change in (proposal.get("changes") or []):
            import re as _re
            for m in _re.finditer(r"parameter[s]?\s+['\"]?(\w+)['\"]?", change, _re.IGNORECASE):
                op_spec["parameters"].append({"name": m.group(1), "type": "string", "required": True, "description": ""})

        handler_ctx = build_handler_context(
            handler_name=expected_name,
            current_file=self._build_context_window(current_file, expected_name, []),
            tool_purpose=tool_purpose,
            skill_name=skill_name,
            verification_mode=verification_mode,
            op_spec=op_spec,
            already_implemented=[],
        )

        existing_section = f"\nEXISTING TOOL CAPABILITIES (do not duplicate):\n{existing_capabilities}\n" if existing_capabilities else ""

        # Inject implementation sketch if proposal provides one for the new handler
        sketch_steps = (proposal.get('implementation_sketch') or {}).get(expected_name, [])
        sketch_section = ""
        if sketch_steps:
            sketch_section = "\nIMPLEMENTATION STEPS (follow these exactly):\n" + "\n".join(sketch_steps) + "\n"

        prompt = f"""TASK: Create NEW handler method for capability.

{handler_ctx}
{sketch_section}
{f"{proposal.get('constraint_block', '')}" if proposal.get('constraint_block') else ""}
CAPABILITY TO ADD:
{proposal['description']}

CHANGES:
{chr(10).join(f"- {c}" for c in proposal['changes'])}

AVAILABLE SERVICES:
{service_context}
{existing_section}{error_context}
CREATE handler method named: {expected_name}

CRITICAL REQUIREMENTS:
1. Method signature: def {expected_name}(self, **kwargs) -> dict
2. Extract ALL expected parameters from kwargs using kwargs.get()
3. Validate required parameters (return {{'error': '...'}}) if missing)
4. Use ONLY self.services.X for operations
5. Return {{'success': True, 'data': ...}} or {{'success': False, 'error': '...'}}
6. Keep under 25 lines
7. NO imports, NO class definition
8. DO NOT call any new self._helper() method unless that helper already exists in the current file context
9. If you need extra logic, implement it inline inside this handler instead of inventing a helper

Return ONLY the method definition."""

        feedback = ""
        for attempt in range(2):
            attempt_prompt = prompt + (f"\n\nVALIDATION FEEDBACK:\n{feedback}\n" if feedback else "")
            try:
                response = self.llm._call_llm(attempt_prompt, temperature=0.2, max_tokens=1500, expect_json=False)
                handler = self._extract_python_code(response)
                if not handler or f"def {expected_name}(" not in handler:
                    feedback = f"Output did not contain def {expected_name}. Return only the method definition."
                    continue

                invalid = self._invalid_service_calls(handler)
                if invalid:
                    feedback = "Invalid self.services calls:\n- " + "\n- ".join(invalid)
                    continue
                invalid_helpers = self._find_undefined_private_helper_calls(
                    handler,
                    expected_name,
                    current_file=current_file,
                )
                if invalid_helpers:
                    feedback = (
                        "Undefined private helper calls detected:\n- "
                        + "\n- ".join(invalid_helpers)
                        + "\nDo not invent helper methods. Reuse existing methods from the file or inline the logic."
                    )
                    continue

                # Verify every code path returns a dict (no implicit None)
                missing_return = self._check_missing_return(handler, expected_name)
                if missing_return:
                    feedback = missing_return
                    continue

                return handler
            except Exception as e:
                logger.warning(f"Failed to generate new handler (attempt {attempt + 1}): {e}")
                feedback = str(e)

        return None
    
    def _check_missing_return(self, handler_code: str, handler_name: str) -> str:
        """Check that the handler has an explicit return on every terminal path.

        Root cause of 'returned None' sandbox failures: LLM generates a handler
        where the happy path falls through to implicit None (missing return in
        try block, or conditional branch without return).

        Returns an error string if a problem is found, empty string if OK.
        """
        try:
            tree = ast.parse(textwrap.dedent(handler_code))
            fn = next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                       and n.name == handler_name), None)
            if not fn:
                return ""

            # Collect all Return nodes in the function
            returns = [n for n in ast.walk(fn) if isinstance(n, ast.Return)]

            # No return at all
            if not returns:
                return (f"{handler_name} has no return statement. "
                        "Every code path MUST return a dict like "
                        "{{'success': True, 'data': ...}} or {{'success': False, 'error': '...'}}")

            # Check for bare return (return None implicitly)
            bare = [r for r in returns if r.value is None]
            if bare:
                return (f"{handler_name} has a bare 'return' with no value on line {bare[0].lineno}. "
                        "Replace with return {{'success': False, 'error': '...'}} or "
                        "return {{'success': True, 'data': result}}")

            # Check last statement of function body is a return
            last = fn.body[-1]
            if not isinstance(last, ast.Return):
                # Last statement is not a return -- could be a try/except or if block
                # that might not cover all paths. Warn but don't hard-fail.
                # The sandbox will catch it if it actually returns None.
                pass

            return ""
        except Exception:
            return ""

    def _extract_operation_name(self, proposal: Dict[str, Any]) -> str:
        """Extract operation name from proposal.

        Priority order:
        1. implementation_sketch keys — the sketch already has the correct
           handler name (_handle_X), so strip the prefix and use it directly.
           This avoids the text-parsing fallback that produced 'handle' instead
           of 'handle_meta_question' and 'search' instead of 'search_tools'.
        2. changes list — look for quoted capability name or _handle_ pattern.
        3. description fallback — skip filler words to get the operation noun.
        """
        # Priority 1: sketch keys are the most reliable source
        sketch = proposal.get('implementation_sketch') or {}
        if sketch:
            # Take the first key, strip _handle_ prefix
            first_key = next(iter(sketch))
            if first_key.startswith('_handle_'):
                return first_key[len('_handle_'):]

        # Priority 2: changes list
        changes = proposal.get('changes', [])
        for change in changes:
            if 'capability named' in change.lower():
                match = re.search(r"['\"]([^'\"]+)['\"]", change)
                if match:
                    return match.group(1)
            if 'handler method' in change.lower() and '_handle_' in change:
                match = re.search(r'_handle_(\w+)', change)
                if match:
                    return match.group(1)

        # Priority 3: description fallback
        description = proposal.get('description', '')
        desc_lower = description.lower()
        SKIP_WORDS = {'capability', 'operation', 'support', 'the', 'a', 'an', 'to', 'for', 'of', 'and', 'with'}
        for keyword in ['add', 'implement', 'create']:
            if keyword in desc_lower:
                words = desc_lower.split()
                if keyword in words:
                    idx = words.index(keyword)
                    for w in words[idx + 1:]:
                        cleaned = re.sub(r'[^a-z0-9_]', '', w)
                        if cleaned and cleaned not in SKIP_WORDS:
                            return cleaned

        for w in desc_lower.split():
            cleaned = re.sub(r'[^a-z0-9_]', '', w)
            if cleaned and cleaned not in SKIP_WORDS:
                return cleaned
        return 'unknown'
    
    def _extract_handler_parameters(self, code: str, handler_name: str) -> List[tuple]:
        """Extract parameters from handler by analyzing kwargs.get() calls.
        Returns list of (param_name, is_required) tuples.
        """
        try:
            import textwrap as _tw
            # Dedent before parsing — handler code extracted from class has 4-space indent
            dedented = _tw.dedent(code)
            tree = ast.parse(dedented)
            
            # Find the handler function
            handler_node = None
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == handler_name:
                    handler_node = node
                    break
            
            if not handler_node:
                return []
            
            params = []
            seen = set()
            
            # Look for kwargs.get('param_name') calls
            for node in ast.walk(handler_node):
                if isinstance(node, ast.Call):
                    # Check if it's kwargs.get()
                    if (isinstance(node.func, ast.Attribute) and 
                        node.func.attr == 'get' and
                        isinstance(node.func.value, ast.Name) and
                        node.func.value.id == 'kwargs'):
                        
                        if node.args and isinstance(node.args[0], ast.Constant):
                            param_name = node.args[0].value
                            if param_name not in seen:
                                # Check if required (no default value or default is None)
                                is_required = len(node.args) == 1 or (
                                    len(node.args) == 2 and 
                                    isinstance(node.args[1], ast.Constant) and 
                                    node.args[1].value is None
                                )
                                params.append((param_name, is_required))
                                seen.add(param_name)
            
            return params
        except Exception as e:
            logger.warning(f"Failed to extract handler parameters: {e}")
            return []
    
    def _insert_handler_before_execute(self, code: str, new_handler: str, class_name: str) -> str:
        """Insert new handler before execute() method."""
        try:
            tree = ast.parse(code)
            class_node = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name), None)
            if not class_node:
                return code
            
            execute_node = next((n for n in class_node.body if isinstance(n, ast.FunctionDef) and n.name == 'execute'), None)
            if not execute_node:
                return code
            
            lines = code.splitlines()
            insert_pos = execute_node.lineno - 1
            
            # Normalize indentation
            normalized = textwrap.dedent(new_handler).strip()
            handler_lines = ["    " + line if line else "" for line in normalized.splitlines()]
            handler_lines.append("")  # Add blank line
            
            lines[insert_pos:insert_pos] = handler_lines
            return "\n".join(lines) + "\n"
        except Exception as e:
            logger.error(f"Failed to insert handler: {e}")
            return code
    
    def _add_capability_registration(self, code: str, proposal: Dict[str, Any], class_name: str) -> str:
        """Add capability registration in register_capabilities."""
        operation_name = self._extract_operation_name(proposal)
        
        # Extract parameters from the generated handler
        handler_params = self._extract_handler_parameters(code, f"_handle_{operation_name}")
        
        # Build parameters list for capability
        _PLURAL_LIST_NAMES = {'datasets', 'keys', 'plans', 'texts', 'workflows', 'items', 'records',
                              'steps', 'results', 'tags', 'ids', 'files', 'paths', 'queries', 'methods'}
        _INTEGER_NAMES = {'limit', 'count', 'max', 'min', 'size', 'num', 'number', 'page',
                          'offset', 'timeout', 'retries', 'priority', 'num_key_points', 'summary_length'}
        if handler_params:
            param_lines = []
            for param_name, is_required in handler_params:
                if param_name in _PLURAL_LIST_NAMES:
                    ptype = 'ParameterType.LIST'
                elif param_name in _INTEGER_NAMES:
                    ptype = 'ParameterType.INTEGER'
                else:
                    ptype = 'ParameterType.STRING'
                param_lines.append(
                    f"                Parameter(name='{param_name}', type={ptype}, "
                    f"description='{param_name} parameter', required={is_required})"
                )
            params_code = "[\n" + ",\n".join(param_lines) + "\n            ]"
        else:
            params_code = "[]"
        
        # Create ToolCapability registration
        registration = f"""        {operation_name}_capability = ToolCapability(
            name="{operation_name}",
            description="{proposal['description'][:80]}",
            parameters={params_code},
            returns="Operation result",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability({operation_name}_capability, self._handle_{operation_name})"""
        
        # Insert before closing of register_capabilities
        try:
            tree = ast.parse(code)
            class_node = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name), None)
            if not class_node:
                return code
            
            reg_node = next((n for n in class_node.body if isinstance(n, ast.FunctionDef) and n.name == 'register_capabilities'), None)
            if not reg_node:
                return code
            
            lines = code.splitlines()
            insert_pos = reg_node.end_lineno - 1  # Before method end
            
            lines.insert(insert_pos, "")
            lines.insert(insert_pos + 1, registration)
            
            return "\n".join(lines) + "\n"
        except Exception as e:
            logger.error(f"Failed to add capability registration: {e}")
            return code
    
    def _add_execute_routing(self, code: str, proposal: Dict[str, Any], class_name: str) -> str:
        """Add routing in execute() method for new operation.

        Supports two execute() patterns:
        1. execute_capability() delegation (structural rule) -- insert before the return line
        2. Legacy manual if/elif with raise ValueError -- insert before the raise

        Root cause of previous failures: the loop stop condition used
        `not lines[i].startswith('        ')` (8-space) to detect the next method,
        but method defs inside a class are at 4-space indent. For single-line
        execute() bodies the loop exited before finding execute_capability.
        Fixed: stop when indent <= execute method's own indent (4 spaces).
        """
        operation_name = self._extract_operation_name(proposal)

        try:
            lines = code.splitlines()

            # Locate execute() method start
            execute_start = None
            execute_indent = 4  # default class method indent
            for i, line in enumerate(lines):
                if re.match(r'\s+def execute\s*\(', line):
                    execute_start = i
                    execute_indent = len(line) - len(line.lstrip())
                    break

            if execute_start is None:
                logger.error("Failed to add execute routing: execute() method not found")
                return code

            # Scan execute() body — stop when we hit the next method at same indent level
            insert_line_idx = None
            for i in range(execute_start + 1, len(lines)):
                line = lines[i]
                stripped = line.lstrip()
                current_indent = len(line) - len(stripped) if stripped else execute_indent + 4

                # Stop at next method/class definition at same or lower indent
                if stripped and current_indent <= execute_indent and re.match(r'def |class ', stripped):
                    break

                # Pattern 1: execute_capability delegation -- insert before this return
                if 'execute_capability' in line and stripped.startswith('return'):
                    insert_line_idx = i
                    break

                # Pattern 2: raise ValueError for unknown operation
                if 'raise ValueError' in line and ('operation' in line or 'Unsupported' in line or 'Unknown' in line):
                    insert_line_idx = i
                    break

            # Fallback: any raise ValueError in execute body
            if insert_line_idx is None:
                for i in range(execute_start + 1, len(lines)):
                    line = lines[i]
                    stripped = line.lstrip()
                    current_indent = len(line) - len(stripped) if stripped else execute_indent + 4
                    if stripped and current_indent <= execute_indent and re.match(r'def |class ', stripped):
                        break
                    if 'raise ValueError' in line:
                        insert_line_idx = i
                        break

            if insert_line_idx is None:
                logger.error("Failed to add execute routing: no insertion point found in execute()")
                return code

            insert_indent = len(lines[insert_line_idx]) - len(lines[insert_line_idx].lstrip())
            new_if = ' ' * insert_indent + f'if operation == "{operation_name}":'
            new_return = ' ' * (insert_indent + 4) + f'return self._handle_{operation_name}(**kwargs)'

            lines.insert(insert_line_idx, '')
            lines.insert(insert_line_idx, new_return)
            lines.insert(insert_line_idx, new_if)

            return '\n'.join(lines) + '\n'
        except Exception as e:
            logger.error(f"Failed to add execute routing: {e}")
            return code
    
    def _build_class_context(self, code: str, class_name: str) -> str:
        """Build a compact class-level context string showing all other methods (signatures only)."""
        try:
            tree = ast.parse(code)
            class_node = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name), None)
            if not class_node:
                return ""
            lines = code.splitlines()
            parts = [f"class {class_name}(BaseTool):"]
            for node in class_node.body:
                if isinstance(node, ast.FunctionDef):
                    sig_line = lines[node.lineno - 1].strip()
                    parts.append(f"    {sig_line}  # ... (existing method)")
            return "\n".join(parts)
        except Exception:
            return ""

    def _improve_single_handler(
        self,
        handler_code: str,
        handler_name: str,
        proposal: Dict[str, Any],
        class_name: str,
        service_context: str,
        sandbox_error: Optional[str] = None,
        validation_error: Optional[str] = None,
        class_context: str = "",
        tool_purpose: str = "",
        skill_name: str = "",
        verification_mode: str = "",
        current_file: str = "",
        already_implemented: Optional[List[str]] = None,
    ) -> Optional[str]:
        """Improve a single handler method."""
        from infrastructure.code_generation.tool_creation.base import build_handler_context

        error_context = ""
        if validation_error:
            error_context = f"\n\nPREVIOUS ATTEMPT FAILED VALIDATION:\n{validation_error}\n\nFIX THE VALIDATION ERRORS ABOVE.\n"
        elif sandbox_error:
            error_context = f"\n\nPREVIOUS ATTEMPT FAILED WITH ERROR:\n{sandbox_error}\n\nFIX THE ERROR ABOVE.\n"

        # Build op_spec from analysis capabilities — try dict first (full spec),
        # then fall back to extracting params from the handler source itself.
        analysis = proposal.get("analysis") or {}
        op_name = handler_name.replace("_handle_", "")
        op_spec: Dict[str, Any] = {}
        for cap in (analysis.get("capabilities") or []):
            if isinstance(cap, dict) and cap.get("name") == op_name:
                op_spec = cap
                break
        # If capabilities are strings (regex-extracted), build op_spec from handler source
        if not op_spec:
            params = self._extract_handler_parameters(handler_code, handler_name)
            if params:
                op_spec = {
                    "parameters": [
                        {"name": n, "type": "string", "required": r, "description": ""}
                        for n, r in params
                    ]
                }

        handler_ctx = build_handler_context(
            handler_name=handler_name,
            current_file=self._build_context_window(current_file or handler_code, handler_name, already_implemented or []),
            tool_purpose=tool_purpose,
            skill_name=skill_name,
            verification_mode=verification_mode,
            op_spec=op_spec,
            already_implemented=already_implemented or [],
        )

        # Inject implementation sketch if proposal provides one for this handler
        sketch_steps = (proposal.get('implementation_sketch') or {}).get(handler_name, [])
        sketch_section = ""
        if sketch_steps:
            sketch_section = "\nIMPLEMENTATION STEPS (follow these exactly):\n" + "\n".join(sketch_steps) + "\n"

        prompt = f"""TASK: Improve this handler method using the edit block format.

{handler_ctx}
{sketch_section}
{f"{proposal.get('constraint_block', '')}" if proposal.get('constraint_block') else ""}
IMPROVEMENT PROPOSAL:
{proposal['description']}

CHANGES TO MAKE:
{chr(10).join(f"- {c}" for c in proposal['changes'])}

AVAILABLE SERVICES (use self.services.X):
{service_context}
{error_context}
Edit block format -- output EXACTLY this structure, nothing else:
<<<< ORIGINAL
{handler_code}
=======
<your improved implementation here>
>>>>

CRITICAL REQUIREMENTS:
- Keep method name: {handler_name}
- Keep method signature unchanged
- ALWAYS use self.services.X - NEVER call self.X directly
- Return plain dict with 'success' key (not ToolResult)
- Keep under 25 lines
- DO NOT add imports
- DO NOT call any new self._helper() method unless that helper already exists in the current file context
- If you need extra logic, implement it inline in this method instead of inventing a helper"""

        feedback = ""
        for attempt in range(3):
            try:
                attempt_prompt = prompt + (f"\n\nVALIDATION FEEDBACK:\n{feedback}\n" if feedback else "")
                response = self.llm._call_llm(attempt_prompt, temperature=0.2, max_tokens=1500, expect_json=False)

                improved = self._parse_edit_block(response, handler_name)
                if not improved:
                    improved = self._extract_method_from_response(response, handler_name)

                if improved and self._validate_handler(improved, handler_name):
                    invalid = self._invalid_service_calls(improved)
                    if invalid:
                        feedback = "Invalid self.services calls detected:\n- " + "\n- ".join(invalid)
                        continue
                    invalid_helpers = self._find_undefined_private_helper_calls(
                        improved,
                        handler_name,
                        current_file=current_file,
                    )
                    if invalid_helpers:
                        feedback = (
                            "Undefined private helper calls detected:\n- "
                            + "\n- ".join(invalid_helpers)
                            + "\nDo not invent helper methods. Reuse existing methods from the file or inline the logic."
                        )
                        continue
                    missing_return = self._check_missing_return(improved, handler_name)
                    if missing_return:
                        feedback = missing_return
                        continue
                    return improved

                feedback = (
                    f"Output did not contain a valid edit block or def {handler_name}.\n"
                    f"Use the exact format:\n<<<< ORIGINAL\n{handler_code}\n=======\n<implementation>\n>>>>"
                )

            except Exception as e:
                logger.warning(f"Handler improvement attempt {attempt + 1} failed: {e}")
                feedback = str(e)

        return None
    
    def _build_context_window(
        self,
        full_code: str,
        current_handler: str,
        already_implemented: List[str],
        max_chars: int = 10000,
    ) -> str:
        """
        Build a focused context window for the LLM instead of sending the full file.

        Includes (in priority order until max_chars):
        1. Class skeleton (signatures only) — always included, cheap
        2. Already-improved handlers in full — LLM must stay consistent with them
        3. The current handler being improved — always included
        4. Remaining handlers as signatures only

        This replaces the hard 12KB char cap which blindly truncated the file
        and could cut off handlers that were already improved this session.
        """
        try:
            tree = ast.parse(full_code)
        except Exception:
            return full_code[:max_chars]

        cls = next((n for n in tree.body if isinstance(n, ast.ClassDef)), None)
        if not cls:
            return full_code[:max_chars]

        src_lines = full_code.splitlines()

        def get_fn_source(node) -> str:
            return "\n".join(src_lines[node.lineno - 1:node.end_lineno])

        def get_fn_sig(node) -> str:
            return "    " + src_lines[node.lineno - 1].strip() + "  # ..."

        # 1. Class header + __init__ + register_capabilities signature
        parts = []
        header = f"class {cls.name}(BaseTool):"
        parts.append(header)
        for node in cls.body:
            if isinstance(node, ast.FunctionDef):
                if node.name in ('__init__', 'register_capabilities', 'execute'):
                    parts.append(get_fn_sig(node))

        skeleton = "\n".join(parts)
        budget = max_chars - len(skeleton)

        # 2. Already-improved handlers in full (most important for consistency)
        improved_blocks = []
        for node in cls.body:
            if isinstance(node, ast.FunctionDef) and node.name in already_implemented:
                src = get_fn_source(node)
                if budget - len(src) > 500:  # keep at least 500 for current handler
                    improved_blocks.append(src)
                    budget -= len(src)

        # 3. Current handler in full
        current_src = ""
        for node in cls.body:
            if isinstance(node, ast.FunctionDef) and node.name == current_handler:
                current_src = get_fn_source(node)
                budget -= len(current_src)
                break

        # 4. Remaining handlers as signatures only
        sig_lines = []
        for node in cls.body:
            if isinstance(node, ast.FunctionDef):
                if node.name in already_implemented or node.name == current_handler:
                    continue
                if node.name in ('__init__', 'register_capabilities', 'execute'):
                    continue
                sig_lines.append(get_fn_sig(node))

        sections = [skeleton]
        if improved_blocks:
            sections.append("\n# --- Already improved this session ---")
            sections.extend(improved_blocks)
        if current_src:
            sections.append("\n# --- Current handler (being improved) ---")
            sections.append(current_src)
        if sig_lines:
            sections.append("\n# --- Other handlers (signatures only) ---")
            sections.extend(sig_lines)

        return "\n".join(sections)

    def _parse_edit_block(self, text: str, handler_name: str):
        """Extract the UPDATED section from an aider-style edit block."""
        if '```' in text:
            text = self._extract_python_code(text)
        
        orig_pos = text.find('<<<< ORIGINAL')
        # Accept 7-char (aider standard) or 4-char separator
        sep_marker = '======='
        sep_pos = text.find(sep_marker, orig_pos + 1 if orig_pos >= 0 else 0)
        if sep_pos < 0:
            sep_marker = '===='
            sep_pos = text.find(sep_marker, orig_pos + 1 if orig_pos >= 0 else 0)
        end_pos = text.find('>>>>', sep_pos + 1 if sep_pos >= 0 else 0)
        
        if orig_pos < 0 or sep_pos < 0 or end_pos < 0:
            return None
        
        updated = text[sep_pos + len(sep_marker):end_pos].strip()
        if not updated or f'def {handler_name}' not in updated:
            return None
        
        return self._extract_method_from_response(updated, handler_name) or updated

    def _extract_class_name(self, code: str) -> Optional[str]:
        """Extract class name from code."""
        match = re.search(r'class\s+(\w+)', code)
        return match.group(1) if match else None
    
    def _extract_handlers(self, code: str, class_name: str) -> Dict[str, str]:
        """Extract all handler methods from class."""
        try:
            tree = ast.parse(code)
            class_node = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name), None)
            if not class_node:
                return {}
            
            handlers = {}
            lines = code.splitlines()
            
            for node in class_node.body:
                if isinstance(node, ast.FunctionDef):
                    # Get all methods (not just _handle_*)
                    if node.name not in ['__init__', 'register_capabilities', 'get_capabilities', 'execute']:
                        handler_code = "\n".join(lines[node.lineno - 1:node.end_lineno])
                        handlers[node.name] = handler_code
            
            return handlers
        except Exception as e:
            logger.error(f"Failed to extract handlers: {e}")
            return {}
    
    def _extract_method_from_response(self, response: str, method_name: str) -> Optional[str]:
        """Extract method from LLM response."""
        code = self._extract_python_code(response)
        if not code:
            return None
        
        code = textwrap.dedent(code).strip()
        
        try:
            tree = ast.parse(code)
            fn = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == method_name), None)
            if fn:
                lines = code.splitlines()
                return "\n".join(lines[fn.lineno - 1:fn.end_lineno])
        except:
            pass
        
        # Fallback: if response is just the method
        if f"def {method_name}(" in code:
            return code
        
        return None
    
    def _replace_handler(
        self,
        code: str,
        handler_name: str,
        improved_handler: str,
        class_name: str
    ) -> str:
        """Replace handler in class code."""
        try:
            tree = ast.parse(code)
            class_node = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name), None)
            if not class_node:
                return code
            
            target = next((n for n in class_node.body if isinstance(n, ast.FunctionDef) and n.name == handler_name), None)
            if not target:
                return code
            
            # Normalize indentation
            normalized = textwrap.dedent(improved_handler).strip("\n")
            replacement_lines = ["    " + line if line else "" for line in normalized.splitlines()]
            
            lines = code.splitlines()
            start = target.lineno - 1
            end = target.end_lineno
            lines[start:end] = replacement_lines
            
            return "\n".join(lines) + "\n"
        except Exception as e:
            logger.error(f"Failed to replace handler: {e}")
            return code
    
    def _validate_handler(self, handler_code: str, expected_name: str) -> bool:
        """Validate handler code."""
        if not handler_code or len(handler_code) < 10:
            return False
        
        if f"def {expected_name}(" not in handler_code:
            return False
        
        try:
            ast.parse(handler_code)
            return True
        except:
            return False

    def _find_undefined_private_helper_calls(
        self,
        handler_code: str,
        handler_name: str,
        current_file: str = "",
    ) -> List[str]:
        """Detect invented self._helper() calls that do not exist in the current file."""
        try:
            tree = ast.parse(textwrap.dedent(handler_code))
        except Exception:
            return []

        defined_methods = set()
        if current_file:
            try:
                file_tree = ast.parse(current_file)
                defined_methods = {
                    node.name
                    for node in ast.walk(file_tree)
                    if isinstance(node, ast.FunctionDef)
                }
            except Exception:
                defined_methods = set()

        issues: List[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute):
                continue
            if not isinstance(func.value, ast.Name) or func.value.id != "self":
                continue
            called = func.attr
            if not called.startswith("_") or called == handler_name:
                continue
            if called in defined_methods:
                continue
            issues.append(f"self.{called}() is not defined in the current file")

        seen = set()
        return [issue for issue in issues if not (issue in seen or seen.add(issue))]
    
    def _extract_tool_structure(self, code: str) -> str:
        """Extract registered capabilities, methods, and services used via AST."""
        lines = []
        try:
            tree = ast.parse(code)
            caps, methods, services_used = [], [], set()
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if node.name not in ('__init__', 'execute', 'register_capabilities'):
                        methods.append(node.name)
                    for child in ast.walk(node):
                        if isinstance(child, ast.Attribute):
                            if (isinstance(child.value, ast.Attribute)
                                    and isinstance(child.value.value, ast.Name)
                                    and child.value.value.id == 'self'
                                    and child.value.attr == 'services'):
                                services_used.add(child.attr)
                if isinstance(node, ast.Call):
                    func = node.func
                    if isinstance(func, ast.Attribute) and func.attr == 'add_capability':
                        for kw in node.keywords:
                            if kw.arg == 'name' and isinstance(kw.value, ast.Constant):
                                caps.append(kw.value.value)
            if caps:
                lines.append(f"Registered capabilities: {', '.join(caps)}")
            if methods:
                lines.append(f"Methods: {', '.join(methods[:20])}")
            if services_used:
                lines.append(f"Services used: {', '.join(sorted(services_used))}")
        except Exception:
            pass
        return '\n'.join(lines) if lines else ''

    def _extract_python_code(self, response: str) -> str:
        """Extract Python code from response."""
        if "```python" in response:
            start = response.find("```python") + 9
            end = response.find("```", start)
            return response[start:end].strip()
        elif "```" in response:
            start = response.find("```") + 3
            end = response.find("```", start)
            return response[start:end].strip()
        
        return response.strip()
