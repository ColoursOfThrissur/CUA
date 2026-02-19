"""
Controlled self-extension flow for new tool creation
"""
from dataclasses import dataclass
from typing import Optional, Any, List, Dict
from pathlib import Path
import logging
import re
import ast
import json
import textwrap
import os
import tempfile
import importlib.util

logger = logging.getLogger(__name__)

@dataclass
class ToolCreationFlow:
    capability_graph: 'CapabilityGraph'
    expansion_mode: 'ExpansionMode'
    growth_budget: 'GrowthBudget'
    
    def create_new_tool(
        self,
        gap_description: str,
        llm_client,
        bypass_budget: bool = False,
        preferred_tool_name: Optional[str] = None,
    ) -> tuple[bool, str]:
        """Complete flow for creating new tool"""
        
        # Step 1: Detect capability gap
        logger.info(f"Capability gap detected: {gap_description}")
        
        # Step 2: LLM proposes tool spec
        tool_spec = self._propose_tool_spec(
            gap_description,
            llm_client,
            preferred_tool_name=preferred_tool_name,
        )
        if not tool_spec:
            return False, "Failed to generate tool spec"
        
        # Step 3: Controller validates graph safety
        can_register, msg = self.capability_graph.register_tool(tool_spec['node'])
        if not can_register:
            return False, f"Graph validation failed: {msg}"
        
        # Step 4: Check growth budget
        if not bypass_budget and not self.growth_budget.can_create_tool():
            return False, "Growth budget exhausted"
        
        # Step 5: Scaffold template
        template = self._scaffold_template(tool_spec)
        
        # Step 6: LLM fills logic only
        filled_code = self._fill_logic(template, tool_spec, llm_client)
        if not filled_code:
            return False, "Failed to generate tool logic"

        # Validate generated code syntax before writing files.
        is_valid, validation_error = self._validate_generated_tool_contract(
            filled_code, tool_spec
        )
        if not is_valid:
            return False, f"Generated tool code invalid: {validation_error}"
        
        # Step 7: Create in experimental namespace
        success, msg = self.expansion_mode.create_experimental_tool(
            tool_spec['name'], filled_code
        )
        if not success:
            return False, msg
        
        # Step 8: Auto-generate minimal tests
        self._generate_tests(tool_spec['name'])
        
        # Step 9: Run sandbox
        sandbox_passed = self._run_sandbox(tool_spec['name'])
        if not sandbox_passed:
            self._cleanup_generated_tool_artifacts(tool_spec["name"])
            return False, "Sandbox validation failed"
        
        # Step 10: Register as experimental
        logger.info(f"Tool registered as experimental: {tool_spec['name']}")
        self.growth_budget.record_tool_creation()
        
        return True, f"Experimental tool created: {tool_spec['name']}"
    
    def _propose_tool_spec(
        self,
        gap_description: str,
        llm_client,
        preferred_tool_name: Optional[str] = None,
    ) -> Optional[dict]:
        """LLM proposes tool specification"""
        prompt = f"""Propose a tool specification for: {gap_description}

Return JSON with:
- name: tool_name
- domain: capability_domain
- inputs: [list of input types]
- outputs: [list of output types]
- dependencies: [list of tool dependencies]
- risk_level: 0.0-1.0
"""
        try:
            response = llm_client._call_llm(prompt, temperature=0.3, expect_json=True)
            if not response:
                return None
            response = llm_client._extract_json(response)
            if not response:
                return None
            spec = response
            if preferred_tool_name:
                locked_name = self._normalize_tool_name(preferred_tool_name)
                if not locked_name:
                    return None
                spec['name'] = locked_name
            else:
                spec['name'] = self._normalize_tool_name(spec.get('name', ''))
                if not spec['name']:
                    return None
            inputs = self._normalize_to_string_list(spec.get('inputs', []))
            outputs = self._normalize_to_string_list(spec.get('outputs', []))
            dependencies = self._normalize_to_string_list(spec.get('dependencies', []))
            domain = str(spec.get('domain', 'general'))
            risk_level = spec.get('risk_level', 0.5)
            try:
                risk_level = float(risk_level)
            except Exception:
                risk_level = 0.5
            risk_level = max(0.0, min(1.0, risk_level))
            
            # Create capability node
            from core.capability_graph import CapabilityNode
            spec['node'] = CapabilityNode(
                tool_name=spec['name'],
                inputs=inputs,
                outputs=outputs,
                domain=domain,
                dependencies=dependencies,
                risk_level=risk_level,
                maturity='experimental'
            )
            return spec
        except Exception as e:
            logger.error(f"Failed to propose tool spec: {e}")
            return None
    
    def _scaffold_template(self, tool_spec: dict) -> str:
        """Generate tool template"""
        return f'''"""
{tool_spec['name']} - Auto-generated tool
"""
from tools.tool_interface import BaseTool
from tools.tool_result import ToolResult, ResultStatus
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel

class {self._class_name_for_tool(tool_spec['name'])}(BaseTool):
    def __init__(self):
        self.name = "{tool_spec['name']}"
        self.description = "{tool_spec.get('description', 'Auto-generated tool')}"
        super().__init__()
    
    def register_capabilities(self):
        """Register tool capabilities"""
        # TODO: LLM fills this
        pass
    
    def execute(self, operation: str, parameters: dict) -> ToolResult:
        """Execute tool operation"""
        # TODO: LLM fills this
        pass
'''
    
    def _fill_logic(self, template: str, tool_spec: dict, llm_client) -> Optional[str]:
        """LLM fills in tool logic"""
        if self._is_qwen_model(llm_client):
            return self._fill_logic_staged_qwen(template, tool_spec, llm_client)
        return self._fill_logic_single_shot(template, tool_spec, llm_client)

    def _fill_logic_single_shot(self, template: str, tool_spec: dict, llm_client) -> Optional[str]:
        prompt_spec = self._tool_spec_prompt_payload(tool_spec)
        prompt = f"""Fill in the logic for this tool template:

{template}

Tool spec:
{json.dumps(prompt_spec, indent=2)}

Operation contract:
{self._operation_contract(prompt_spec)}

Contract reference:
{self._contract_pack()}

Hard requirements:
- Keep the class name exactly: {self._class_name_for_tool(tool_spec['name'])}
- Keep self.name exactly: "{tool_spec['name']}"
- In register_capabilities(), call self.add_capability(...) at least once
- Do NOT assign self.capabilities directly
- Implement execute(self, operation: str, parameters: dict)

Return only complete Python code with register_capabilities and execute methods implemented.
"""
        return self._generate_with_validation(llm_client, prompt, tool_spec, attempts=3, temperature=0.2)

    def _fill_logic_staged_qwen(self, template: str, tool_spec: dict, llm_client) -> Optional[str]:
        """Two-stage generation tuned for local Qwen models."""
        contract = self._contract_pack()
        prompt_spec = self._tool_spec_prompt_payload(tool_spec)
        # Qwen-hardening: build Stage-1 skeleton deterministically to avoid
        # repeated contract drift in long prompt generations.
        skeleton = self._build_deterministic_stage1_scaffold(prompt_spec, tool_spec)
        is_valid, validation_error = self._validate_generated_tool_contract(skeleton, tool_spec)
        if not is_valid and "does not reference required capability parameters" in str(validation_error):
            logger.warning(
                "Deterministic Stage-1 reported handler-reference drift; continuing with deterministic scaffold: %s",
                validation_error,
            )
            is_valid = True

        if not is_valid:
            logger.warning("Deterministic Stage-1 scaffold invalid, falling back to LLM: %s", validation_error)
            operation_contract = self._operation_contract(prompt_spec)
            stage1_prompt = f"""Stage 1/2: Produce a CONTRACT-COMPLIANT skeleton only.

Template:
{template}

Tool spec:
{json.dumps(prompt_spec, indent=2)}

Operation contract:
{operation_contract}

Contract reference:
{contract}

Requirements:
- Keep class name exactly: {self._class_name_for_tool(tool_spec['name'])}
- Keep self.name exactly: "{tool_spec['name']}"
- Implement register_capabilities with valid ToolCapability and Parameter objects
- Every ToolCapability must include: name, description, parameters, returns, safety_level, examples, dependencies
- ToolCapability.returns must be a STRING description (not list/object)
- Bind capabilities with self.add_capability(capability_obj, self._handler)
- Implement execute(self, operation: str, parameters: dict) dispatch only
- Define private handler stubs used by add_capability bindings
- Handler bodies can be placeholders

Return only complete Python code.
"""
            skeleton = self._generate_with_validation(
                llm_client, stage1_prompt, tool_spec, attempts=3, temperature=0.1
            )
        if not skeleton:
            return None

        return self._fill_logic_staged_qwen_incremental(
            skeleton=skeleton,
            tool_spec=tool_spec,
            prompt_spec=prompt_spec,
            contract=contract,
            llm_client=llm_client,
        )

    def _fill_logic_staged_qwen_incremental(
        self,
        skeleton: str,
        tool_spec: dict,
        prompt_spec: dict,
        contract: str,
        llm_client,
    ) -> Optional[str]:
        """Stage 2 for Qwen: implement one method at a time to reduce context drift."""
        code = skeleton
        stage_targets = self._get_qwen_stage_targets(code, tool_spec)
        if not stage_targets:
            logger.warning("Qwen staged generation found no method targets; fallback to full Stage 2")
            operation_contract = self._operation_contract(prompt_spec)
            stage2_prompt = f"""Stage 2/2: Implement the handler bodies and real logic.

Tool spec:
{json.dumps(prompt_spec, indent=2)}

Operation contract:
{operation_contract}

Contract reference:
{contract}

Requirements:
- Keep imports, class name, self.name, register_capabilities signatures, add_capability bindings, and execute signature unchanged
- Implement logic for create/read/list style operations from the tool spec
- Use consistent ToolResult objects with required fields
- Preserve local-only behavior
- Use deterministic local paths under data/ (never use './')

Return only complete Python code.
"""
            return self._generate_with_validation(
                llm_client, stage2_prompt, tool_spec, attempts=3, temperature=0.15
            )

        for method_name in stage_targets:
            next_code = self._generate_qwen_method_step(
                current_code=code,
                method_name=method_name,
                prompt_spec=prompt_spec,
                contract=contract,
                tool_spec=tool_spec,
                llm_client=llm_client,
            )
            if not next_code:
                return None
            code = next_code

        is_valid, validation_error = self._validate_generated_tool_contract(code, tool_spec)
        if not is_valid:
            logger.warning("Final staged code failed validation: %s", validation_error)
            return None
        return code

    def _build_deterministic_stage1_scaffold(self, prompt_spec: dict, tool_spec: dict) -> str:
        """Build a contract-compliant scaffold without LLM for Qwen stability."""
        tool_name = tool_spec["name"]
        class_name = self._class_name_for_tool(tool_name)
        operations = self._extract_operations_from_prompt_spec(prompt_spec)

        capability_blocks: List[str] = []
        for op in operations:
            op_name = op["name"]
            params = op.get("parameters", [])
            param_lines = []
            for p in params:
                p_name = p.get("name", "param")
                p_desc = p.get("description", f"Parameter {p_name}")
                p_type = self._parameter_type_from_spec(p.get("type"))
                required = bool(p.get("required", True))
                default = p.get("default")
                extra = []
                extra.append(f"required={repr(required)}")
                if default is not None:
                    extra.append(f"default={repr(default)}")
                extra_text = ", " + ", ".join(extra) if extra else ""
                param_lines.append(
                    f'            Parameter(name={p_name!r}, type=ParameterType.{p_type}, description={p_desc!r}{extra_text})'
                )
            params_block = "[\n" + ",\n".join(param_lines) + "\n        ]" if param_lines else "[]"
            handler = f"_handle_{op_name}"
            capability_blocks.append(
                f"""        {op_name}_capability = ToolCapability(
            name={op_name!r},
            description={f"{op_name} operation".title()!r},
            parameters={params_block},
            returns="Operation result payload",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability({op_name}_capability, self.{handler})"""
            )

        register_body = "\n\n".join(capability_blocks) if capability_blocks else "        pass"

        dispatch_lines = []
        dispatch_lines.extend(
            [
                "        parameters = parameters or {}",
                "        if not isinstance(parameters, dict):",
                "            return ToolResult(",
                "                tool_name=self.name,",
                "                capability_name=operation,",
                "                status=ResultStatus.FAILURE,",
                "                data=None,",
                "                error_message=\"parameters must be a dict\"",
                "            )",
            ]
        )
        for op in operations:
            op_name = op["name"]
            handler = f"_handle_{op_name}"
            keyword = "if" if not dispatch_lines else "elif"
            # Choose if/elif based on whether op clauses already started.
            op_keyword = "if" if not any(l.strip().startswith(("if operation", "elif operation")) for l in dispatch_lines) else "elif"
            dispatch_lines.append(f"        {op_keyword} operation == {op_name!r}:")
            dispatch_lines.append(f"            return self.{handler}(**parameters)")
        dispatch_lines.extend(
            [
                "        return ToolResult(",
                "            tool_name=self.name,",
                "            capability_name=operation,",
                "            status=ResultStatus.FAILURE,",
                "            data=None,",
                "            error_message=f\"Unsupported operation: {operation}\"",
                "        )",
            ]
        )
        execute_body = "\n".join(dispatch_lines)

        handler_blocks = []
        for op in operations:
            handler = f"_handle_{op['name']}"
            required_params = [
                p.get("name")
                for p in op.get("parameters", [])
                if p.get("name") and bool(p.get("required", True))
            ]
            required_list_repr = repr(required_params)
            required_reads = "\n".join(
                [f"        _required_{name} = kwargs.get({name!r})" for name in required_params]
            )
            if required_reads:
                required_reads += "\n"
            handler_blocks.append(
                f"""    def {handler}(self, **kwargs) -> ToolResult:
{required_reads}\
        required_params = {required_list_repr}
        missing = [p for p in required_params if kwargs.get(p) in (None, "")]
        if missing:
            return ToolResult(
                tool_name=self.name,
                capability_name={op['name']!r},
                status=ResultStatus.FAILURE,
                data=None,
                error_message=f"Missing required parameters: {{', '.join(missing)}}"
            )
        return ToolResult(
            tool_name=self.name,
            capability_name={op['name']!r},
            status=ResultStatus.FAILURE,
            data=None,
            error_message="Handler not implemented"
        )"""
            )
        handlers_text = "\n\n".join(handler_blocks)

        code = f'''"""
{tool_name} - Auto-generated tool
"""
from tools.tool_interface import BaseTool
from tools.tool_result import ToolResult, ResultStatus
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel

class {class_name}(BaseTool):
    def __init__(self):
        self.name = "{tool_name}"
        self.description = "Auto-generated tool"
        super().__init__()

    def register_capabilities(self):
        """Register tool capabilities"""
{register_body}

    def execute(self, operation: str, parameters: dict) -> ToolResult:
        """Execute tool operation"""
{execute_body}

{handlers_text}
'''
        return code

    def _extract_operations_from_prompt_spec(self, prompt_spec: dict) -> List[dict]:
        ops: List[dict] = []
        for item in prompt_spec.get("inputs", []):
            if not isinstance(item, dict):
                continue
            name = item.get("operation")
            if not isinstance(name, str) or not name.strip():
                continue
            params = item.get("parameters", [])
            if not isinstance(params, list):
                params = []
            normalized_params = []
            for p in params:
                if isinstance(p, dict):
                    p_name = p.get("name")
                    p_type = p.get("type")
                    if not p_name or not p_type:
                        continue
                    required, default = self._normalize_parameter_requirement(p)
                    normalized = dict(p)
                    normalized["required"] = required
                    if default is not None:
                        normalized["default"] = default
                    normalized_params.append(normalized)
            ops.append({"name": name.strip(), "parameters": normalized_params})
        return ops

    def _parameter_type_from_spec(self, raw_type: Optional[str]) -> str:
        t = str(raw_type or "").strip().lower()
        if t in {"string", "str", "text"}:
            return "STRING"
        if t in {"integer", "int", "number"}:
            return "INTEGER"
        if t in {"bool", "boolean"}:
            return "BOOLEAN"
        if t in {"dict", "object", "map"}:
            return "DICT"
        if "path" in t or "file" in t:
            return "FILE_PATH"
        return "LIST" if "list" in t else "STRING"

    def _normalize_parameter_requirement(self, parameter_spec: dict) -> tuple[bool, Any]:
        """Normalize required/default flags from varied LLM schemas."""
        default = parameter_spec.get("default", parameter_spec.get("default_value"))

        if "required" in parameter_spec:
            required = self._coerce_bool(parameter_spec.get("required"), default=True)
        elif "optional" in parameter_spec:
            optional = self._coerce_bool(parameter_spec.get("optional"), default=False)
            required = not optional
        elif default is not None:
            required = False
        else:
            required = True

        # Required fields should not carry defaults in scaffold metadata.
        if required and default is not None:
            default = None
        return required, default

    def _coerce_bool(self, value: Any, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes", "y", "required"}:
                return True
            if lowered in {"false", "0", "no", "n", "optional"}:
                return False
        return default

    def _generate_qwen_method_step(
        self,
        current_code: str,
        method_name: str,
        prompt_spec: dict,
        contract: str,
        tool_spec: dict,
        llm_client,
    ) -> Optional[str]:
        """Generate one method only, merge it, and validate before moving on."""
        current_method = self._extract_method_from_class_code(current_code, tool_spec, method_name)
        if not current_method:
            logger.warning("Could not extract method '%s' from staged code", method_name)
            return None

        method_contract = self._operation_contract_for_method(prompt_spec, method_name)
        feedback = ""
        for _ in range(3):
            prompt = f"""Stage 2/2 (method step): implement ONLY one method.

Target class: {self._class_name_for_tool(tool_spec['name'])}
Target method: {method_name}

Current method:
```python
{current_method}
```

Method-specific contract:
{method_contract}

Global contract:
{contract}

Hard constraints:
- Output ONLY one method: def {method_name}(...)
- Keep the method signature exactly unchanged
- Do NOT output class definitions, imports, or any other methods
- Keep behavior local-only (no network calls)
- Use deterministic paths under data/ (never './')
- Return ToolResult with required fields and valid ResultStatus values

Return only Python method code.
"""
            if feedback:
                prompt = f"{prompt}\n\n{feedback}"

            raw = llm_client._call_llm(prompt, temperature=0.1, expect_json=False)
            if not raw:
                feedback = "Previous output was empty. Return exactly one method."
                continue

            method_code = self._extract_target_method_from_response(raw, method_name)
            if not method_code:
                feedback = f"Could not find 'def {method_name}(...)' in your output. Return exactly that one method."
                continue
            if "./" in method_code:
                feedback = "Do not use './' in paths. Use deterministic data/ paths."
                continue

            merged = self._replace_method_in_class_code(current_code, tool_spec, method_name, method_code)
            if not merged:
                feedback = f"Could not merge method '{method_name}'. Keep signature unchanged and return one method only."
                continue

            is_valid, validation_error = self._validate_generated_tool_contract(merged, tool_spec)
            if is_valid:
                return merged
            repaired = self._attempt_auto_repair(merged, tool_spec, validation_error)
            if repaired and repaired != merged:
                repaired_valid, repaired_error = self._validate_generated_tool_contract(repaired, tool_spec)
                if repaired_valid:
                    logger.info("Method-step auto-repair recovered '%s' after validation failure", method_name)
                    return repaired
                validation_error = repaired_error
            feedback = (
                "Previous output failed validation.\n"
                f"Issue: {validation_error}\n"
                "Regenerate ONLY the target method and preserve the signature."
            )

        fallback = self._build_method_fallback(method_name)
        if fallback:
            merged = self._replace_method_in_class_code(current_code, tool_spec, method_name, fallback)
            if merged:
                is_valid, validation_error = self._validate_generated_tool_contract(merged, tool_spec)
                if is_valid:
                    logger.info("Method-step fallback recovered '%s' after repeated generation failures", method_name)
                    return merged

        logger.warning("Method-step generation failed for '%s'", method_name)
        return None

    def _build_method_fallback(self, method_name: str) -> Optional[str]:
        """Deterministic fallback for fragile staged methods on local models."""
        if method_name == "_handle_list":
            return """def _handle_list(self, **kwargs) -> ToolResult:
        limit = kwargs.get("limit", 10)
        if not isinstance(limit, int):
            return ToolResult(
                tool_name=self.name,
                capability_name="list",
                status=ResultStatus.FAILURE,
                data=None,
                error_message="Invalid type for 'limit'. Expected integer."
            )
        if limit < 1 or limit > 200:
            return ToolResult(
                tool_name=self.name,
                capability_name="list",
                status=ResultStatus.FAILURE,
                data=None,
                error_message="'limit' must be between 1 and 200."
            )

        try:
            base = Path("data")
            if not base.exists():
                return ToolResult(
                    tool_name=self.name,
                    capability_name="list",
                    status=ResultStatus.SUCCESS,
                    data={"items": []},
                    error_message=None
                )

            files = sorted(
                [p for p in base.rglob("*") if p.is_file()],
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )[:limit]
            items = [{"path": str(p)} for p in files]
            return ToolResult(
                tool_name=self.name,
                capability_name="list",
                status=ResultStatus.SUCCESS,
                data={"items": items},
                error_message=None
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                capability_name="list",
                status=ResultStatus.FAILURE,
                data=None,
                error_message=f"Failed to list persisted records: {str(e)}"
            )"""
        return None

    def _get_qwen_stage_targets(self, code: str, tool_spec: dict) -> List[str]:
        """Get ordered method targets: handlers in register_capabilities, then execute."""
        try:
            tree = ast.parse(code)
        except Exception:
            return []

        class_name = self._class_name_for_tool(tool_spec["name"])
        class_node = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name), None)
        if class_node is None:
            return []

        methods = {n.name: n for n in class_node.body if isinstance(n, ast.FunctionDef)}
        register_method = methods.get("register_capabilities")
        if register_method is None:
            return []

        targets: List[str] = []
        for call in self._iter_calls_in_order(register_method):
            if not (isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name)):
                continue
            if call.func.value.id != "self" or call.func.attr != "add_capability":
                continue

            handler_name = None
            if len(call.args) >= 2 and isinstance(call.args[1], ast.Attribute):
                attr = call.args[1]
                if isinstance(attr.value, ast.Name) and attr.value.id == "self":
                    handler_name = attr.attr
            if handler_name is None:
                for kw in call.keywords:
                    if kw.arg == "handler_func" and isinstance(kw.value, ast.Attribute):
                        attr = kw.value
                        if isinstance(attr.value, ast.Name) and attr.value.id == "self":
                            handler_name = attr.attr
                            break

            if handler_name and handler_name in methods and handler_name not in targets:
                targets.append(handler_name)

        # Keep execute deterministic from scaffold; focus LLM on handler logic only.
        return targets

    def _iter_calls_in_order(self, node):
        """Yield ast.Call nodes preserving statement order."""
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Call):
                yield child
            yield from self._iter_calls_in_order(child)

    def _extract_method_from_class_code(self, code: str, tool_spec: dict, method_name: str) -> Optional[str]:
        try:
            tree = ast.parse(code)
        except Exception:
            return None
        class_name = self._class_name_for_tool(tool_spec["name"])
        class_node = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name), None)
        if class_node is None:
            return None
        method_node = next((n for n in class_node.body if isinstance(n, ast.FunctionDef) and n.name == method_name), None)
        if method_node is None:
            return None
        lines = code.splitlines()
        return "\n".join(lines[method_node.lineno - 1:method_node.end_lineno])

    def _extract_target_method_from_response(self, response: str, method_name: str) -> Optional[str]:
        code = self._extract_python_code(response)
        if not code:
            return None
        code = textwrap.dedent(code).strip()

        # Case 1: response is a single method.
        try:
            tree = ast.parse(code)
            fn = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == method_name), None)
            if fn:
                lines = code.splitlines()
                return "\n".join(lines[fn.lineno - 1:fn.end_lineno])
        except Exception:
            pass

        # Case 2: response includes a class/file; extract method from class body.
        try:
            tree = ast.parse(code)
            for class_node in [n for n in tree.body if isinstance(n, ast.ClassDef)]:
                fn = next((n for n in class_node.body if isinstance(n, ast.FunctionDef) and n.name == method_name), None)
                if fn:
                    lines = code.splitlines()
                    return "\n".join(lines[fn.lineno - 1:fn.end_lineno])
        except Exception:
            return None
        return None

    def _replace_method_in_class_code(
        self, code: str, tool_spec: dict, method_name: str, method_code: str
    ) -> Optional[str]:
        try:
            tree = ast.parse(code)
        except Exception:
            return None

        class_name = self._class_name_for_tool(tool_spec["name"])
        class_node = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name), None)
        if class_node is None:
            return None
        target = next((n for n in class_node.body if isinstance(n, ast.FunctionDef) and n.name == method_name), None)
        if target is None:
            return None

        normalized = textwrap.dedent(method_code).strip("\n")
        if not normalized.startswith(f"def {method_name}("):
            return None

        replacement_lines = ["    " + line if line else "" for line in normalized.splitlines()]
        lines = code.splitlines()
        start = target.lineno - 1
        end = target.end_lineno
        lines[start:end] = replacement_lines
        return "\n".join(lines) + "\n"

    def _operation_contract_for_method(self, prompt_spec: dict, method_name: str) -> str:
        if method_name == "execute":
            return (
                "- Dispatch strictly by operation string.\n"
                "- Accept parameters as dict from execute(operation, parameters).\n"
                "- Route to registered handlers and return ToolResult.\n"
                "- Unsupported operations return ResultStatus.FAILURE with clear error_message."
            )

        op_name = method_name
        if method_name.startswith("_handle_"):
            op_name = method_name[len("_handle_"):]
        elif method_name.startswith("_"):
            op_name = method_name[1:]

        for op in prompt_spec.get("inputs", []):
            if not isinstance(op, dict):
                continue
            if op.get("operation") != op_name:
                continue
            params = op.get("parameters", [])
            extras = []
            if op_name == "create":
                extras.extend(
                    [
                        "- Validate required parameters with clear errors.",
                        "- Do not invent or rename parameter keys; use exactly the names listed above.",
                        "- For writes under data/, create parent dirs before open(..., 'w').",
                        "- Persist created data to local storage (do not return success without writing).",
                        "- Use deterministic local paths and return structured ToolResult.",
                    ]
                )
            elif op_name in {"get", "list"}:
                extras.extend(
                    [
                        "- Do not invent or rename parameter keys; use exactly the names listed above.",
                        "- Read from persisted local storage under data/ (no hardcoded fixtures or simulated lists).",
                        "- Keep behavior local-only and deterministic.",
                    ]
                )
            else:
                extras.extend(
                    [
                        "- Do not invent or rename parameter keys; use exactly the names listed above.",
                        "- Keep behavior local-only and deterministic.",
                    ]
                )
            return (
                f"- Operation: {op_name}\n"
                f"- Parameters: {json.dumps(params, indent=2)}\n"
                + "\n".join(extras)
            )
        return f"- Operation hint inferred from method: {op_name}"

    def _generate_with_validation(
        self,
        llm_client,
        base_prompt: str,
        tool_spec: dict,
        attempts: int,
        temperature: float,
    ) -> Optional[str]:
        feedback = ""
        try:
            for _ in range(attempts):
                prompt = f"{base_prompt}\n\n{feedback}" if feedback else base_prompt
                raw = llm_client._call_llm(prompt, temperature=temperature, expect_json=False)
                if not raw:
                    feedback = "Previous output was empty. Return complete Python code only."
                    continue
                code = self._extract_python_code(raw)
                code = self._sanitize_qwen_output(code)

                is_valid, validation_error = self._validate_generated_tool_contract(code, tool_spec)
                if not is_valid:
                    repaired = self._attempt_auto_repair(code, tool_spec, validation_error)
                    if repaired and repaired != code:
                        repaired_valid, repaired_error = self._validate_generated_tool_contract(repaired, tool_spec)
                        if repaired_valid:
                            logger.info("Auto-repair recovered generated tool after validation failure")
                            return repaired
                        validation_error = repaired_error
                if is_valid:
                    return code
                feedback = self._build_retry_feedback(validation_error)
                logger.warning("Tool generation retry due to validation error: %s", validation_error)
            return None
        except Exception as e:
            logger.error(f"Failed to fill logic: {e}")
            return None

    def _extract_python_code(self, response: str) -> str:
        """Extract Python from markdown fences; fallback to raw response."""
        if not response:
            return response

        fenced = re.findall(r"```(?:python)?\s*([\s\S]*?)```", response, flags=re.IGNORECASE)
        if fenced:
            return fenced[0].strip()
        return response.strip()

    def _sanitize_qwen_output(self, code: str) -> str:
        """Normalize common local-model formatting glitches before validation."""
        if not code:
            return code

        text = code.strip()
        lines = text.splitlines()

        # Fix malformed header pattern:
        # LocalPlanMemoryTool - Auto-generated tool
        # """
        if len(lines) >= 2:
            first = lines[0].strip()
            second = lines[1].strip()
            if first.endswith(" - Auto-generated tool") and second == '"""':
                lines.insert(0, '"""')
                text = "\n".join(lines)
                lines = text.splitlines()

        # Drop accidental leading prose before first Python-significant line.
        start_idx = 0
        for idx, line in enumerate(lines):
            s = line.strip()
            if (
                s.startswith('"""')
                or s.startswith("from ")
                or s.startswith("import ")
                or s.startswith("class ")
            ):
                start_idx = idx
                break
        if start_idx > 0:
            text = "\n".join(lines[start_idx:])

        return text.strip()

    def _attempt_auto_repair(self, code: str, tool_spec: dict, validation_error: str) -> Optional[str]:
        """Apply deterministic repair passes for common Qwen drift patterns."""
        if not code:
            return None

        repaired = code
        error_lower = validation_error.lower()

        if "line " in error_lower:
            repaired = self._sanitize_qwen_output(repaired)

        if "parameter(...)" in error_lower and "optional" in error_lower:
            maybe = self._repair_parameter_optional_keyword(repaired)
            if maybe:
                repaired = maybe

        if "toolcapability(...) missing required fields" in error_lower:
            maybe = self._repair_missing_toolcapability_fields(repaired, tool_spec)
            if maybe:
                repaired = maybe

        if "self.add_capability(...) must include capability and handler" in error_lower:
            maybe = self._repair_add_capability_signature(repaired)
            if maybe:
                repaired = maybe

        if "self.add_capability(...) must use handler_func keyword, not handler" in error_lower:
            maybe = self._repair_add_capability_handler_keyword(repaired)
            if maybe:
                repaired = maybe

        if "deterministic data/" in error_lower:
            repaired = repaired.replace("./data/", "data/").replace("./data\\", "data\\")
            repaired = repaired.replace("./", "")

        if "symbol '" in error_lower and "is used but not imported" in error_lower:
            match = re.search(r"Symbol '([A-Za-z_][A-Za-z0-9_]*)' is used but not imported", validation_error)
            if match:
                maybe = self._repair_missing_symbol_import(repaired, match.group(1))
                if maybe:
                    repaired = maybe

        return repaired

    def _repair_missing_symbol_import(self, code: str, symbol: str) -> Optional[str]:
        """Insert missing imports for common generated symbols."""
        import_map = {
            "Path": "from pathlib import Path",
            "json": "import json",
            "core": "import core",
        }
        import_line = import_map.get(symbol)
        if not import_line:
            return None
        lines = code.splitlines()
        if any(line.strip() == import_line for line in lines):
            return None

        # Insert after module docstring and existing imports.
        insert_at = 0
        if lines and lines[0].lstrip().startswith('"""'):
            # Skip docstring block.
            for idx in range(1, len(lines)):
                if lines[idx].rstrip().endswith('"""'):
                    insert_at = idx + 1
                    break
        while insert_at < len(lines):
            s = lines[insert_at].strip()
            if not s or s.startswith("import ") or s.startswith("from "):
                insert_at += 1
                continue
            break

        lines.insert(insert_at, import_line)
        return "\n".join(lines)

    def _repair_missing_toolcapability_fields(self, code: str, tool_spec: dict) -> Optional[str]:
        """Add required ToolCapability keywords when missing."""
        try:
            tree = ast.parse(code)
        except Exception:
            return None

        changed = False
        class_name = self._class_name_for_tool(tool_spec["name"])

        for class_node in [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name]:
            for method in [n for n in class_node.body if isinstance(n, ast.FunctionDef)]:
                for call in [n for n in ast.walk(method) if isinstance(n, ast.Call)]:
                    if not (isinstance(call.func, ast.Name) and call.func.id == "ToolCapability"):
                        continue

                    kw_names = {k.arg for k in call.keywords if k.arg}
                    if "examples" not in kw_names:
                        call.keywords.append(
                            ast.keyword(arg="examples", value=ast.List(elts=[], ctx=ast.Load()))
                        )
                        changed = True
                    if "dependencies" not in kw_names:
                        call.keywords.append(
                            ast.keyword(arg="dependencies", value=ast.List(elts=[], ctx=ast.Load()))
                        )
                        changed = True
                    if "returns" not in kw_names:
                        call.keywords.append(
                            ast.keyword(
                                arg="returns",
                                value=ast.Constant(value="Operation result payload")
                            )
                        )
                        changed = True

        if not changed:
            return None
        try:
            return ast.unparse(tree)
        except Exception:
            return None

    def _repair_add_capability_signature(self, code: str) -> Optional[str]:
        """Normalize add_capability keyword names to expected contract."""
        try:
            tree = ast.parse(code)
        except Exception:
            return None

        changed = False
        for call in [n for n in ast.walk(tree) if isinstance(n, ast.Call)]:
            if not isinstance(call.func, ast.Attribute):
                continue
            if not (isinstance(call.func.value, ast.Name) and call.func.value.id == "self"):
                continue
            if call.func.attr != "add_capability":
                continue

            new_keywords = []
            for kw in call.keywords:
                if kw.arg == "capability_obj":
                    new_keywords.append(ast.keyword(arg="capability", value=kw.value))
                    changed = True
                elif kw.arg == "handler":
                    new_keywords.append(ast.keyword(arg="handler_func", value=kw.value))
                    changed = True
                else:
                    new_keywords.append(kw)
            call.keywords = new_keywords

        if not changed:
            return None
        try:
            return ast.unparse(tree)
        except Exception:
            return None

    def _repair_add_capability_handler_keyword(self, code: str) -> Optional[str]:
        """Rename add_capability(handler=...) to handler_func=..."""
        return self._repair_add_capability_signature(code)

    def _repair_parameter_optional_keyword(self, code: str) -> Optional[str]:
        """Convert Parameter(optional=...) to Parameter(required=not optional)."""
        try:
            tree = ast.parse(code)
        except Exception:
            return None

        changed = False
        for call in [n for n in ast.walk(tree) if isinstance(n, ast.Call)]:
            if not (isinstance(call.func, ast.Name) and call.func.id == "Parameter"):
                continue
            new_keywords = []
            for kw in call.keywords:
                if kw.arg == "optional":
                    # required = not optional
                    required_value = True
                    if isinstance(kw.value, ast.Constant):
                        required_value = not bool(kw.value.value)
                    new_keywords.append(ast.keyword(arg="required", value=ast.Constant(value=required_value)))
                    changed = True
                else:
                    new_keywords.append(kw)
            call.keywords = new_keywords

            if not any(k.arg == "required" for k in call.keywords if k.arg):
                call.keywords.append(ast.keyword(arg="required", value=ast.Constant(value=True)))
                changed = True

        if not changed:
            return None
        try:
            return ast.unparse(tree)
        except Exception:
            return None
    
    def _generate_tests(self, tool_name: str):
        """Auto-generate minimal tests"""
        # Already handled by expansion_mode.create_experimental_tool
        pass

    def _cleanup_generated_tool_artifacts(self, tool_name: str):
        """Delete generated tool/test artifacts when post-generation validation fails."""
        tool_file = Path(getattr(self.expansion_mode, "experimental_dir", "tools/experimental")) / f"{tool_name}.py"
        test_file = Path("tests/experimental") / f"test_{tool_name}.py"
        for p in (tool_file, test_file):
            try:
                p.unlink(missing_ok=True)
            except Exception as e:
                logger.warning("Failed cleaning generated artifact %s: %s", p, e)
    
    def _run_sandbox(self, tool_name: str) -> bool:
        """Run runtime playground validation for a newly generated tool."""
        tool_path = Path(getattr(self.expansion_mode, "experimental_dir", "tools/experimental")) / f"{tool_name}.py"
        if not tool_path.exists():
            logger.warning("Sandbox skipped: tool file not found at %s", tool_path)
            return False

        try:
            tool_class = self._load_tool_class_from_file(tool_name, tool_path)
            if tool_class is None:
                logger.error("Sandbox failed: could not resolve tool class for %s", tool_name)
                return False

            original_cwd = Path.cwd()
            with tempfile.TemporaryDirectory(prefix=f"tool_sandbox_{tool_name}_") as temp_dir:
                os.chdir(temp_dir)
                try:
                    os.makedirs("data", exist_ok=True)
                    tool_instance = tool_class()
                    return self._run_tool_playground_smoke(tool_instance)
                finally:
                    os.chdir(original_cwd)
        except Exception as e:
            logger.error("Sandbox failed for %s: %s", tool_name, e)
            return False

    def _load_tool_class_from_file(self, tool_name: str, tool_path: Path):
        """Load generated tool class from file path without modifying runtime registries."""
        module_name = f"_sandbox_{tool_name.lower()}_{abs(hash(str(tool_path)))}"
        spec = importlib.util.spec_from_file_location(module_name, str(tool_path))
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        class_name = self._class_name_for_tool(tool_name)
        return getattr(module, class_name, None)

    def _run_tool_playground_smoke(self, tool_instance) -> bool:
        """Execute a deterministic smoke sequence across discovered capabilities."""
        from core.tool_orchestrator import ToolOrchestrator

        capabilities = tool_instance.get_capabilities()
        if not capabilities:
            logger.error("Sandbox failed: generated tool has no capabilities")
            return False

        orchestrator = ToolOrchestrator()
        shared = {
            "id": "demo-001",
            "task_id": "demo-001",
            "contact_id": "demo-001",
            "plan_id": "demo-001",
            "name": "Demo User",
            "email": "demo@example.com",
            "notes": "sandbox validation",
            "summary": "sandbox validation",
        }

        operations = list(capabilities.keys())
        ordered_ops = [op for op in ("create", "save", "append", "get", "read", "list", "recent") if op in operations]
        ordered_ops.extend(op for op in operations if op not in ordered_ops)

        for op in ordered_ops:
            capability = capabilities.get(op)
            params = self._build_playground_parameters(capability, shared)
            result = orchestrator.execute_tool_step(
                tool=tool_instance,
                tool_name=getattr(tool_instance, "name", tool_instance.__class__.__name__),
                operation=op,
                parameters=params,
                context={},
            )
            if not result.success:
                logger.error("Sandbox failed for operation '%s': %s", op, result.error)
                return False

        return True

    def _build_playground_parameters(self, capability, shared: Dict[str, Any]) -> Dict[str, Any]:
        """Build deterministic test parameters from capability metadata."""
        from tools.tool_capability import ParameterType

        params: Dict[str, Any] = {}
        for p in getattr(capability, "parameters", []) or []:
            name = getattr(p, "name", None)
            if not name:
                continue
            if name in shared:
                params[name] = shared[name]
                continue
            default = getattr(p, "default", None)
            required = bool(getattr(p, "required", True))
            p_type = getattr(p, "type", None)
            if default is not None:
                params[name] = default
            elif required:
                if p_type == ParameterType.STRING:
                    params[name] = f"demo_{name}"
                elif p_type == ParameterType.INTEGER:
                    params[name] = 3
                elif p_type == ParameterType.BOOLEAN:
                    params[name] = True
                elif p_type == ParameterType.LIST:
                    params[name] = ["demo"]
                elif p_type == ParameterType.DICT:
                    params[name] = {"source": "sandbox"}
                elif p_type == ParameterType.FILE_PATH:
                    params[name] = f"data/{name}.txt"
                else:
                    params[name] = f"demo_{name}"
        return params

    def _normalize_to_string_list(self, value: Any) -> List[str]:
        """Normalize LLM-provided fields into list[str]."""
        if value is None:
            return []
        if not isinstance(value, list):
            value = [value]

        result: List[str] = []
        for item in value:
            if isinstance(item, str):
                s = item.strip()
                if s:
                    result.append(s)
                continue
            if isinstance(item, dict):
                for key in ("name", "id", "type", "value"):
                    v = item.get(key)
                    if isinstance(v, str) and v.strip():
                        result.append(v.strip())
                        break
                else:
                    result.append(str(item))
                continue
            result.append(str(item))
        return result

    def _class_name_for_tool(self, tool_name: str) -> str:
        return ''.join((part[:1].upper() + part[1:]) for part in tool_name.split('_') if part)

    def _normalize_tool_name(self, raw_name: str) -> str:
        if not raw_name:
            return ""
        cleaned = re.sub(r'[^A-Za-z0-9_]+', '_', str(raw_name)).strip('_')
        if not cleaned:
            return ""
        if cleaned[0].isdigit():
            cleaned = f"tool_{cleaned}"
        return cleaned

    def _is_qwen_model(self, llm_client) -> bool:
        model = str(getattr(llm_client, "model", "")).lower()
        return "qwen" in model

    def _contract_pack(self) -> str:
        return """Required API contracts:
- Parameter(name=..., type=ParameterType.<STRING|INTEGER|BOOLEAN|LIST|DICT|FILE_PATH>, description=..., required=..., default=...)
- ToolCapability(name=..., description=..., parameters=[...], returns="string description", safety_level=SafetyLevel.<LOW|MEDIUM|HIGH|CRITICAL>, examples=[...], dependencies=[...])
- self.add_capability(capability_obj, self._handler)  # or keywords: capability=..., handler_func=...
- execute(self, operation: str, parameters: dict)
- ToolResult(tool_name=self.name, capability_name=operation, status=ResultStatus.<...>, data=..., error_message=...)
- If writing files under data/, call Path(...).mkdir(parents=True, exist_ok=True) or os.makedirs(..., exist_ok=True) before open(..., 'w'/'a'/'x')
- Prefer using core.storage_broker.get_storage_broker(self.name) for reads/writes when applicable
Disallowed patterns:
- self.capabilities = ...
- ToolCapability(operation=...)
- ToolResult(success=..., message=..., record=..., records=...)
- self.add_capability(..., handler=...)
- ResultStatus.ERROR (use ResultStatus.FAILURE)
- mutable default args like tags=[], metadata={}"""

    def _build_retry_feedback(self, validation_error: str) -> str:
        issue_hint = ""
        if "add_capability" in validation_error:
            issue_hint = (
                "\nUse exactly one of:\n"
                "1) self.add_capability(capability_obj, self._handle_op)\n"
                "2) self.add_capability(capability=capability_obj, handler_func=self._handle_op)\n"
                "Do NOT use handler=."
            )
        elif "Unsupported ParameterType" in validation_error:
            issue_hint = (
                "\nUse only: STRING, INTEGER, BOOLEAN, LIST, DICT, FILE_PATH."
            )
        elif "ToolCapability(..., returns=...) must be a string description" in validation_error:
            issue_hint = (
                "\nSet returns to a plain string, e.g. returns=\"Operation result payload\"."
            )
        elif "ToolCapability(...) missing required fields" in validation_error:
            issue_hint = (
                "\nInclude ALL ToolCapability fields: name, description, parameters, returns, safety_level, examples, dependencies."
            )
        elif "Parameter(...) must use required=..., not optional=..." in validation_error:
            issue_hint = (
                "\nUse required=True/False in Parameter(...). Do NOT use optional=..."
            )
        elif "mutable default argument" in validation_error:
            issue_hint = "\nNever use [] or {} as defaults; use None and initialize inside."
        elif "deterministic data/" in validation_error:
            issue_hint = "\nUse deterministic paths under data/, not './' relative directories."
        elif "writes under data/ but does not create directories first" in validation_error:
            issue_hint = (
                "\nBefore writing files under data/, create directories first, e.g. "
                "Path(target).parent.mkdir(parents=True, exist_ok=True)."
            )

        return (
            "Previous output failed validation.\n"
            f"Issue: {validation_error}\n"
            f"{issue_hint}\n"
            "Regenerate full code and follow these exact signatures:\n"
            f"{self._contract_pack()}"
        )

    def _tool_spec_prompt_payload(self, tool_spec: dict) -> dict:
        """Sanitize tool spec before embedding in prompts."""
        return {
            "name": tool_spec.get("name"),
            "domain": tool_spec.get("domain"),
            "inputs": tool_spec.get("inputs", []),
            "outputs": tool_spec.get("outputs", []),
            "dependencies": tool_spec.get("dependencies", []),
            "risk_level": tool_spec.get("risk_level", 0.5),
        }

    def _operation_contract(self, prompt_spec: dict) -> str:
        inputs = prompt_spec.get("inputs", [])
        if not isinstance(inputs, list) or not inputs:
            return "- Define at least one operation with explicit parameters."

        lines: List[str] = []
        for op in inputs:
            if isinstance(op, dict):
                op_name = op.get("operation", "<operation>")
                params = op.get("parameters")
                if isinstance(params, list):
                    names = []
                    for p in params:
                        if isinstance(p, dict):
                            pname = p.get("name")
                            ptype = p.get("type")
                            if pname and ptype:
                                names.append(f"{pname}:{ptype}")
                            elif pname:
                                names.append(str(pname))
                    param_text = ", ".join(names) if names else "no-params"
                else:
                    extras = [k for k in op.keys() if k != "operation"]
                    param_text = ", ".join(extras) if extras else "no-params"
                lines.append(f"- {op_name}: {param_text}")
            else:
                lines.append(f"- {op}")
        return "\n".join(lines)

    def _validate_generated_tool_contract(self, code: str, tool_spec: dict) -> tuple[bool, str]:
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"line {e.lineno}: {e.msg}"
        except Exception as e:
            return False, str(e)

        expected_class_name = self._class_name_for_tool(tool_spec['name'])
        class_defs = [n for n in tree.body if isinstance(n, ast.ClassDef)]
        if not class_defs:
            return False, "No class definition found"
        target_class = None
        for class_def in class_defs:
            if class_def.name == expected_class_name:
                target_class = class_def
                break
        if target_class is None:
            return False, f"Expected class '{expected_class_name}' not found"

        methods = {
            n.name: n for n in target_class.body if isinstance(n, ast.FunctionDef)
        }
        register_method = methods.get("register_capabilities")
        if not register_method:
            return False, "register_capabilities() missing"
        execute_method = methods.get("execute")
        if not execute_method:
            return False, "execute() missing"

        execute_params = [arg.arg for arg in execute_method.args.args]
        if len(execute_params) < 2 or execute_params[0] != "self" or execute_params[1] != "operation":
            return False, "execute() signature must start with (self, operation)"
        supports_parameters_dict = len(execute_params) >= 3 and execute_params[2] == "parameters"
        has_kwargs = execute_method.args.kwarg is not None
        if not supports_parameters_dict and not has_kwargs:
            return False, "execute() must accept parameters dict or **kwargs"

        class_method_names = {
            m.name for m in target_class.body if isinstance(m, ast.FunctionDef)
        }

        has_add_capability = False
        bad_add_capability_signature = False
        invalid_add_capability_keyword = False
        missing_handler_method = None
        allowed_parameter_types = {"STRING", "INTEGER", "BOOLEAN", "LIST", "DICT", "FILE_PATH"}
        for node in ast.walk(register_method):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "self":
                    if node.func.attr == "add_capability":
                        has_add_capability = True
                        if node.keywords:
                            keyword_names = {k.arg for k in node.keywords if k.arg}
                            if "handler" in keyword_names:
                                invalid_add_capability_keyword = True
                            if not ({"capability", "handler_func"} <= keyword_names):
                                bad_add_capability_signature = True
                            for kw in node.keywords:
                                if kw.arg == "handler_func" and isinstance(kw.value, ast.Attribute):
                                    if isinstance(kw.value.value, ast.Name) and kw.value.value.id == "self":
                                        if kw.value.attr not in class_method_names:
                                            missing_handler_method = kw.value.attr
                        elif len(node.args) < 2:
                            bad_add_capability_signature = True
                        else:
                            handler = node.args[1]
                            if isinstance(handler, ast.Attribute):
                                if isinstance(handler.value, ast.Name) and handler.value.id == "self":
                                    if handler.attr not in class_method_names:
                                        missing_handler_method = handler.attr
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "Parameter":
                    keyword_names = {k.arg for k in node.keywords if k.arg}
                    if "description" not in keyword_names:
                        return False, "Parameter(...) must include description=..."
                    if "optional" in keyword_names:
                        return False, "Parameter(...) must use required=..., not optional=..."
                    if "required" in keyword_names and "default" in keyword_names:
                        required_kw = next((k for k in node.keywords if k.arg == "required"), None)
                        default_kw = next((k for k in node.keywords if k.arg == "default"), None)
                        if (
                            isinstance(required_kw.value, ast.Constant)
                            and required_kw.value.value is True
                            and isinstance(default_kw.value, ast.Constant)
                            and default_kw.value.value is not None
                        ):
                            return False, "Parameter(...) cannot be required=True when default is set"
                    for kw in node.keywords:
                        if kw.arg == "type" and isinstance(kw.value, ast.Attribute):
                            if isinstance(kw.value.value, ast.Name) and kw.value.value.id == "ParameterType":
                                if kw.value.attr not in allowed_parameter_types:
                                    return False, f"Unsupported ParameterType.{kw.value.attr}"
                if isinstance(node.func, ast.Name) and node.func.id == "ToolCapability":
                    keyword_names = {k.arg for k in node.keywords if k.arg}
                    required = {"name", "description", "parameters", "returns", "safety_level", "examples"}
                    if "operation" in keyword_names:
                        return False, "ToolCapability(...) must use name=..., not operation=..."
                    if node.keywords and not required.issubset(keyword_names):
                        return False, "ToolCapability(...) missing required fields"
                    for kw in node.keywords:
                        if kw.arg == "returns":
                            if not (isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str)):
                                return False, "ToolCapability(..., returns=...) must be a string description"
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Attribute):
                        if isinstance(target.value, ast.Name) and target.value.id == "self" and target.attr == "capabilities":
                            return False, "register_capabilities() must not assign self.capabilities directly"
        if not has_add_capability:
            return False, "register_capabilities() must call self.add_capability(...)"
        if invalid_add_capability_keyword:
            return False, "self.add_capability(...) must use handler_func keyword, not handler"
        if bad_add_capability_signature:
            return False, "self.add_capability(...) must include capability and handler"
        if missing_handler_method:
            return False, f"add_capability handler method '{missing_handler_method}' not found in class"

        bad_tool_result_fields = {"success", "message", "record", "records"}
        required_tool_result_fields = {"tool_name", "capability_name", "status"}
        allowed_statuses = {"SUCCESS", "FAILURE", "PARTIAL", "TIMEOUT", "CANCELLED"}
        for node in ast.walk(target_class):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name) or node.func.id != "ToolResult":
                continue
            kw_names = {k.arg for k in node.keywords if k.arg}
            if kw_names & bad_tool_result_fields:
                return False, "ToolResult(...) uses unsupported fields"
            if node.keywords and not required_tool_result_fields.issubset(kw_names):
                return False, "ToolResult(...) missing required fields: tool_name, capability_name, status"
            if not node.keywords and len(node.args) < 3:
                return False, "ToolResult(...) must include tool_name, capability_name, and status"
            for kw in node.keywords:
                if kw.arg == "status" and isinstance(kw.value, ast.Attribute):
                    if isinstance(kw.value.value, ast.Name) and kw.value.value.id == "ResultStatus":
                        if kw.value.attr not in allowed_statuses:
                            return False, f"Unsupported ResultStatus.{kw.value.attr}"

        for node in ast.walk(target_class):
            if not isinstance(node, ast.FunctionDef):
                continue
            defaults = list(node.args.defaults) + [d for d in node.args.kw_defaults if d is not None]
            for default in defaults:
                if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                    return False, f"Function '{node.name}' uses mutable default argument"
                if isinstance(default, ast.Call) and isinstance(default.func, ast.Name):
                    if default.func.id in {"list", "dict", "set"}:
                        return False, f"Function '{node.name}' uses mutable default argument"

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
                        return False, "Use deterministic data/ paths instead of './' paths"

        undefined_helper = self._find_undefined_private_helper_call(target_class)
        if undefined_helper:
            return False, undefined_helper

        path_mismatch_error = self._validate_create_get_storage_consistency(target_class)
        if path_mismatch_error:
            return False, path_mismatch_error

        write_dir_error = self._validate_data_write_directory_preparation(target_class)
        if write_dir_error:
            return False, write_dir_error

        isinstance_error = self._validate_isinstance_parameter_type_usage(target_class)
        if isinstance_error:
            return False, isinstance_error

        handler_contract_error = self._validate_handler_param_contract_alignment(register_method, target_class)
        if handler_contract_error:
            return False, handler_contract_error

        static_list_error = self._validate_non_persistent_list_handler(target_class)
        if static_list_error:
            return False, static_list_error

        crud_persistence_error = self._validate_crud_persistence_contract(register_method, target_class)
        if crud_persistence_error:
            return False, crud_persistence_error

        import_error = self._validate_common_symbol_imports(tree)
        if import_error:
            return False, import_error

        has_name_assignment = False
        for method in target_class.body:
            if not isinstance(method, ast.FunctionDef) or method.name != "__init__":
                continue
            for node in ast.walk(method):
                if not isinstance(node, ast.Assign):
                    continue
                for target in node.targets:
                    if (
                        isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "self"
                        and target.attr == "name"
                        and isinstance(node.value, ast.Constant)
                        and node.value.value == tool_spec["name"]
                    ):
                        has_name_assignment = True
        if not has_name_assignment:
            return False, f"__init__ must set self.name to '{tool_spec['name']}'"

        return True, ""

    def _find_undefined_private_helper_call(self, target_class: ast.ClassDef) -> Optional[str]:
        """Detect calls to private self helpers that are not defined in class."""
        class_methods = {
            m.name for m in target_class.body if isinstance(m, ast.FunctionDef)
        }
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

    def _validate_create_get_storage_consistency(self, target_class: ast.ClassDef) -> Optional[str]:
        """Ensure create/get handlers use consistent data/ storage roots when both exist."""
        methods = {
            m.name: m for m in target_class.body if isinstance(m, ast.FunctionDef)
        }
        create_method = methods.get("_handle_create")
        get_method = methods.get("_handle_get")
        if not create_method or not get_method:
            return None

        create_roots = self._collect_data_path_roots(create_method)
        get_roots = self._collect_data_path_roots(get_method)
        if not create_roots or not get_roots:
            return None
        if create_roots.isdisjoint(get_roots):
            return (
                "Storage path mismatch between _handle_create and _handle_get "
                "(use a shared data/ subdirectory pattern)"
            )
        return None

    def _collect_data_path_roots(self, method: ast.FunctionDef) -> set:
        roots = set()
        for node in ast.walk(method):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name) or node.func.id != "open":
                continue
            if not node.args:
                continue
            path_text = self._ast_path_text(node.args[0])
            if not path_text:
                continue
            root = self._extract_data_root(path_text)
            if root:
                roots.add(root)
        return roots

    def _ast_path_text(self, node: ast.AST) -> Optional[str]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.JoinedStr):
            parts = []
            for v in node.values:
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    parts.append(v.value)
                else:
                    parts.append("{}")
            return "".join(parts)
        return None

    def _extract_data_root(self, path_text: str) -> Optional[str]:
        normalized = path_text.replace("\\", "/")
        if "data/" not in normalized:
            return None
        tail = normalized.split("data/", 1)[1]
        if not tail:
            return "__data_root__"
        segment = tail.split("/", 1)[0]
        if not segment or "{" in segment or "}" in segment or "." in segment:
            return "__data_root__"
        return segment

    def _validate_data_write_directory_preparation(self, target_class: ast.ClassDef) -> Optional[str]:
        """Reject write handlers that write into data/ paths without ensuring directories exist."""
        for method in [m for m in target_class.body if isinstance(m, ast.FunctionDef)]:
            writes_to_data = False
            has_dir_prepare = False
            for node in ast.walk(method):
                if not isinstance(node, ast.Call):
                    continue
                if self._is_data_write_open_call(node):
                    writes_to_data = True
                if self._is_directory_prepare_call(node):
                    has_dir_prepare = True
            if writes_to_data and not has_dir_prepare:
                return (
                    f"Method '{method.name}' writes under data/ but does not create directories first "
                    "(use Path(...).mkdir(parents=True, exist_ok=True) or os.makedirs(..., exist_ok=True))"
                )
        return None

    def _is_data_write_open_call(self, call: ast.Call) -> bool:
        if not (isinstance(call.func, ast.Name) and call.func.id == "open"):
            return False
        if not call.args:
            return False
        path_text = self._ast_path_text(call.args[0])
        if not path_text or "data/" not in path_text.replace("\\", "/"):
            return False
        mode = self._extract_open_mode(call)
        return any(flag in mode for flag in ("w", "a", "x"))

    def _extract_open_mode(self, call: ast.Call) -> str:
        if len(call.args) >= 2 and isinstance(call.args[1], ast.Constant) and isinstance(call.args[1].value, str):
            return call.args[1].value
        for kw in call.keywords:
            if kw.arg == "mode" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                return kw.value.value
        return "r"

    def _is_directory_prepare_call(self, call: ast.Call) -> bool:
        # os.makedirs(path, exist_ok=True)
        if isinstance(call.func, ast.Attribute):
            if isinstance(call.func.value, ast.Name) and call.func.value.id == "os" and call.func.attr == "makedirs":
                return self._has_true_exist_ok(call)
            # Path(...).mkdir(parents=True, exist_ok=True)
            if call.func.attr == "mkdir":
                return self._has_true_exist_ok(call)
        return False

    def _has_true_exist_ok(self, call: ast.Call) -> bool:
        for kw in call.keywords:
            if kw.arg == "exist_ok" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                return True
        return False

    def _validate_isinstance_parameter_type_usage(self, target_class: ast.ClassDef) -> Optional[str]:
        """Reject isinstance(..., ParameterType.X) - second arg must be runtime type."""
        for method in [m for m in target_class.body if isinstance(m, ast.FunctionDef)]:
            for node in ast.walk(method):
                if not isinstance(node, ast.Call):
                    continue
                if not (isinstance(node.func, ast.Name) and node.func.id == "isinstance"):
                    continue
                if len(node.args) < 2:
                    continue
                second = node.args[1]
                if (
                    isinstance(second, ast.Attribute)
                    and isinstance(second.value, ast.Name)
                    and second.value.id == "ParameterType"
                ):
                    return (
                        f"Method '{method.name}' uses isinstance(..., ParameterType.{second.attr}); "
                        "use concrete Python types (str, int, bool, list, dict) instead"
                    )
        return None

    def _validate_handler_param_contract_alignment(
        self, register_method: ast.FunctionDef, target_class: ast.ClassDef
    ) -> Optional[str]:
        """Ensure handler required keys align with capability parameter definitions."""
        contract = self._extract_capability_contract(register_method)
        if not contract:
            return None

        methods = {m.name: m for m in target_class.body if isinstance(m, ast.FunctionDef)}
        for cap_name, spec in contract.items():
            handler_name = f"_handle_{cap_name}"
            handler = methods.get(handler_name)
            if not handler:
                continue

            all_params = set(spec.get("parameters", []))
            required_params = set(spec.get("required", []))
            used_keys = self._collect_kwargs_keys(handler)

            # Required params should be referenced by handler logic.
            missing_used = [p for p in sorted(required_params) if p not in used_keys]
            if missing_used:
                return (
                    f"Handler '{handler_name}' does not reference required capability parameters: {missing_used}"
                )

            # Detect drift in required_params dict keys that are outside capability contract.
            drift_keys = self._collect_required_params_dict_keys(handler)
            extra = [k for k in sorted(drift_keys) if k not in all_params]
            if extra:
                return (
                    f"Handler '{handler_name}' validates unknown required keys {extra} "
                    f"not present in capability '{cap_name}' parameters"
                )
        return None

    def _extract_capability_contract(self, register_method: ast.FunctionDef) -> Dict[str, Dict[str, List[str]]]:
        """Extract capability params/required from ToolCapability declarations."""
        contract: Dict[str, Dict[str, List[str]]] = {}
        for node in ast.walk(register_method):
            if not isinstance(node, ast.Call):
                continue
            if not (isinstance(node.func, ast.Name) and node.func.id == "ToolCapability"):
                continue
            cap_name = None
            params: List[str] = []
            required: List[str] = []
            for kw in node.keywords:
                if kw.arg == "name":
                    if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        cap_name = kw.value.value
                elif kw.arg == "parameters" and isinstance(kw.value, ast.List):
                    for elem in kw.value.elts:
                        if not (isinstance(elem, ast.Call) and isinstance(elem.func, ast.Name) and elem.func.id == "Parameter"):
                            continue
                        pname = None
                        prequired = True
                        if elem.args and isinstance(elem.args[0], ast.Constant) and isinstance(elem.args[0].value, str):
                            pname = elem.args[0].value
                        for pkw in elem.keywords:
                            if pkw.arg == "name" and isinstance(pkw.value, ast.Constant) and isinstance(pkw.value.value, str):
                                pname = pkw.value.value
                            if pkw.arg == "required" and isinstance(pkw.value, ast.Constant):
                                prequired = bool(pkw.value.value)
                        if pname:
                            params.append(pname)
                            if prequired:
                                required.append(pname)
            if cap_name:
                contract[cap_name] = {"parameters": params, "required": required}
        return contract

    def _collect_kwargs_keys(self, method: ast.FunctionDef) -> set:
        keys = set()
        for node in ast.walk(method):
            # kwargs.get("name")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if (
                    isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "kwargs"
                    and node.func.attr == "get"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                ):
                    keys.add(node.args[0].value)
            # kwargs["name"]
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "kwargs":
                slice_node = node.slice
                if isinstance(slice_node, ast.Constant) and isinstance(slice_node.value, str):
                    keys.add(slice_node.value)
        return keys

    def _collect_required_params_dict_keys(self, method: ast.FunctionDef) -> set:
        keys = set()
        for node in ast.walk(method):
            if not isinstance(node, ast.Assign):
                continue
            if not any(isinstance(t, ast.Name) and t.id == "required_params" for t in node.targets):
                continue
            if not isinstance(node.value, ast.Dict):
                continue
            for key in node.value.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    keys.add(key.value)
        return keys

    def _validate_non_persistent_list_handler(self, target_class: ast.ClassDef) -> Optional[str]:
        """Reject list handlers that return hardcoded mock records without storage reads."""
        method = next(
            (m for m in target_class.body if isinstance(m, ast.FunctionDef) and m.name == "_handle_list"),
            None,
        )
        if not method:
            return None

        has_storage_read = False
        has_hardcoded_record_list = False

        for node in ast.walk(method):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "open":
                    mode = self._extract_open_mode(node)
                    if "r" in mode or mode == "r":
                        has_storage_read = True
                if isinstance(node.func, ast.Attribute):
                    # storage.read(...)
                    if node.func.attr in {"read", "read_json", "list_files", "glob"}:
                        has_storage_read = True
            if isinstance(node, ast.List) and node.elts and all(isinstance(e, ast.Dict) for e in node.elts):
                has_hardcoded_record_list = True

        if has_hardcoded_record_list and not has_storage_read:
            return (
                "_handle_list appears to use hardcoded mock records without reading persisted data"
            )
        return None

    def _validate_crud_persistence_contract(
        self, register_method: ast.FunctionDef, target_class: ast.ClassDef
    ) -> Optional[str]:
        """Enforce create/get/list persistence semantics for generated local CRUD tools."""
        contract = self._extract_capability_contract(register_method)
        if not contract:
            return None

        methods = {m.name: m for m in target_class.body if isinstance(m, ast.FunctionDef)}
        has_create = "create" in contract

        if has_create:
            create_handler = methods.get("_handle_create")
            if (
                create_handler
                and not self._is_placeholder_handler(create_handler)
                and not self._handler_writes_storage(create_handler)
            ):
                return (
                    "Handler '_handle_create' must persist data to local storage "
                    "(expected write under data/ or storage broker write)"
                )

            get_handler = methods.get("_handle_get")
            if (
                "get" in contract
                and get_handler
                and not self._is_placeholder_handler(get_handler)
                and not self._handler_reads_storage(get_handler)
            ):
                return (
                    "Handler '_handle_get' must read from persisted local storage "
                    "(mock/simulated lookup detected)"
                )

            list_handler = methods.get("_handle_list")
            if (
                "list" in contract
                and list_handler
                and not self._is_placeholder_handler(list_handler)
                and not self._handler_reads_storage(list_handler)
            ):
                return (
                    "Handler '_handle_list' must read from persisted local storage "
                    "(mock/simulated listing detected)"
                )
        return None

    def _is_placeholder_handler(self, method: ast.FunctionDef) -> bool:
        """Detect stage scaffold placeholder handlers."""
        for node in ast.walk(method):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and "Handler not implemented" in node.value
            ):
                return True
        return False

    def _handler_reads_storage(self, method: ast.FunctionDef) -> bool:
        """Detect file/storage read access in a handler."""
        for node in ast.walk(method):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name) and node.func.id == "open":
                mode = self._extract_open_mode(node)
                if "r" in mode or mode == "r":
                    return True
            if isinstance(node.func, ast.Attribute):
                if node.func.attr in {"read", "read_text", "read_json", "list_files", "glob", "iterdir"}:
                    return True
        return False

    def _handler_writes_storage(self, method: ast.FunctionDef) -> bool:
        """Detect file/storage write access in a handler."""
        for node in ast.walk(method):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name) and node.func.id == "open":
                mode = self._extract_open_mode(node)
                if any(flag in mode for flag in ("w", "a", "x")):
                    return True
            if isinstance(node.func, ast.Attribute):
                if node.func.attr in {"write", "write_text", "write_json", "append", "dump"}:
                    return True
        return False

    def _validate_common_symbol_imports(self, tree: ast.Module) -> Optional[str]:
        """Catch missing imports for common generated symbols (Path/core/json)."""
        imported = set()
        assigned = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add((alias.asname or alias.name.split(".")[0]))
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

        required_symbols = {"Path", "core", "json"}
        used = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                if node.id in required_symbols:
                    used.add(node.id)

        for sym in sorted(used):
            if sym not in imported and sym not in assigned:
                return f"Symbol '{sym}' is used but not imported"
        return None
