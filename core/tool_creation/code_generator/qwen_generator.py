"""
Qwen-specific code generator with multi-stage LLM generation
Generates code in stages to keep each LLM call under 200 lines for accuracy
"""
import json
import logging
import ast
from typing import Optional, List
from .base import BaseCodeGenerator

logger = logging.getLogger(__name__)


class QwenCodeGenerator(BaseCodeGenerator):
    """Multi-stage generation optimized for local Qwen models"""
    
    def generate(self, template: str, tool_spec: dict) -> Optional[str]:
        """Generate using multi-stage LLM approach: skeleton → handlers one-by-one"""
        from core.tool_creation.validator import ToolValidator
        
        self._creation_id = tool_spec.get('_creation_id')
        correction_prompt = tool_spec.get('_correction_prompt')
        retry_attempt = tool_spec.get('_retry_attempt', 0)

        generation_meta = tool_spec.get("_generation_meta")
        if not isinstance(generation_meta, dict):
            generation_meta = {}
        # Always overwrite per-run.
        generation_meta.update(
            {
                "stage1_valid": False,
                "stage2_attempted": False,
                "stage2_valid": False,
                "stage2_error": None,
            }
        )
        tool_spec["_generation_meta"] = generation_meta
        
        if correction_prompt:
            logger.info(f"Retry attempt {retry_attempt} with correction guidance")
        
        prompt_spec = self._build_prompt_spec(tool_spec)
        contract = self._build_contract_pack(tool_spec.get('target_category'))
        
        skeleton = self._generate_stage1_skeleton(prompt_spec, tool_spec, contract, correction_prompt)
        if not skeleton:
            logger.error("Stage 1 skeleton generation failed")
            return None
        
        try:
            if self._creation_id:
                from core.tool_creation_logger import get_tool_creation_logger
                get_tool_creation_logger().log_artifact(self._creation_id, "generated_skeleton", "stage1", skeleton)
        except:
            pass
        
        validator = ToolValidator()
        is_valid, validation_error = validator.validate(skeleton, tool_spec)
        if not is_valid:
            logger.warning(f"Stage 1 skeleton validation failed: {validation_error}")
            return None

        generation_meta["stage1_valid"] = True
        
        final_code = self._generate_stage2_handlers(skeleton, prompt_spec, tool_spec, contract)
        if not final_code:
            logger.warning("Stage 2 handler generation failed; falling back to validated stage 1 scaffold")
            generation_meta["stage2_attempted"] = True
            generation_meta["stage2_error"] = "Stage 2 handler generation returned empty/None"
            return skeleton

        try:
            if self._creation_id:
                from core.tool_creation_logger import get_tool_creation_logger
                get_tool_creation_logger().log_artifact(self._creation_id, "final_code", "stage2", final_code)
        except:
            pass
        
        is_valid, validation_error = validator.validate(final_code, tool_spec)
        if not is_valid:
            logger.warning(f"Final code validation failed: {validation_error}. Falling back to validated stage 1 scaffold")
            generation_meta["stage2_attempted"] = True
            generation_meta["stage2_error"] = f"Stage 2 code failed validation: {validation_error}"
            try:
                if self._creation_id:
                    from core.tool_creation_logger import get_tool_creation_logger
                    get_tool_creation_logger().log_artifact(
                        self._creation_id,
                        "stage2_validation_failed",
                        "stage2",
                        {"error": validation_error},
                    )
            except Exception:
                pass
            return skeleton

        generation_meta["stage2_attempted"] = True
        generation_meta["stage2_valid"] = True
        
        logger.info("Multi-stage Qwen generation completed successfully")
        return final_code
    
    def _generate_stage1_skeleton(self, prompt_spec: dict, tool_spec: dict, contract: str, correction_prompt: str = None) -> Optional[str]:
        """Stage 1: Deterministic contract-compliant scaffold.

        Local models frequently hallucinate BaseTool APIs (e.g., register_capability/register_tool_capability)
        or misuse ToolCapability fields (e.g., ToolCapability(function=...)). Those failures block creation
        before the system can even get to evolution.

        This generator produces a minimal scaffold without LLM calls:
        - register_capabilities() uses self.add_capability(capability, handler)
        - execute() dispatches through BaseTool.execute_capability()
        - handler stubs exist for every declared operation so stage 2 can fill them in
        """
        tool_name = tool_spec.get("name") or "New_Tool"
        class_name = self._class_name(tool_name)
        operations = prompt_spec.get("inputs", []) or []
        if not operations:
            operations = [{"operation": "execute", "parameters": []}]
        return self._build_deterministic_scaffold(class_name, tool_spec, operations)

    def _build_deterministic_scaffold(self, class_name: str, tool_spec: dict, operations: list) -> str:
        domain = tool_spec.get("domain") or tool_spec.get("description") or "Tool"
        dependencies = tool_spec.get("dependencies") or []
        safety = self._safety_level_from_risk(tool_spec.get("risk_level", 0.5))

        lines: List[str] = []
        lines.append("from tools.tool_interface import BaseTool")
        lines.append("from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel")
        lines.append("")
        lines.append(f"class {class_name}(BaseTool):")
        lines.append("    def __init__(self, orchestrator=None):")
        lines.append(f"        self.description = {json.dumps(str(domain))}")
        lines.append("        self.services = orchestrator.get_services(self.__class__.__name__) if orchestrator else None")
        lines.append("        super().__init__()")
        lines.append("")
        lines.append("    def register_capabilities(self):")

        for op in operations:
            op_name = self._safe_capability_name(op.get("operation") if isinstance(op, dict) else None)
            params = op.get("parameters", []) if isinstance(op, dict) else []
            cap_var = f"{op_name}_capability"

            param_exprs = self._render_parameter_exprs(params)

            lines.append(f"        {cap_var} = ToolCapability(")
            lines.append(f"            name={json.dumps(op_name)},")
            lines.append(f"            description={json.dumps(f'Operation: {op_name}')},")
            lines.append("            parameters=[")
            for expr in param_exprs:
                lines.append(f"                {expr},")
            lines.append("            ],")
            lines.append('            returns="dict",')
            lines.append(f"            safety_level=SafetyLevel.{safety},")
            lines.append("            examples=[{}],")
            if dependencies:
                lines.append(f"            dependencies={json.dumps([str(d) for d in dependencies])},")
            lines.append("        )")
            lines.append(f"        self.add_capability({cap_var}, self._handle_{op_name})")
            lines.append("")

        if not operations:
            lines.append("        pass")
            lines.append("")

        lines.append("    def execute(self, operation: str, **kwargs):")
        lines.append("        return self.execute_capability(operation, **kwargs)")

        for op in operations:
            op_name = self._safe_capability_name(op.get("operation") if isinstance(op, dict) else None)
            lines.append("")
            lines.append(f"    def _handle_{op_name}(self, **kwargs):")
            lines.append("        # Stage 2 fills in real logic; keep sandbox-safe default.")
            lines.append(f"        return {{\"operation\": {json.dumps(op_name)}, \"received\": kwargs, \"status\": \"stub\"}}")

        return "\n".join(lines).rstrip() + "\n"

    def _render_parameter_exprs(self, params: list) -> List[str]:
        if not isinstance(params, list) or not params:
            return []

        type_mapping = {
            "array": "LIST",
            "list": "LIST",
            "date": "STRING",
            "datetime": "STRING",
            "timestamp": "STRING",
            "number": "INTEGER",
            "float": "INTEGER",
            "int": "INTEGER",
            "integer": "INTEGER",
            "object": "DICT",
            "json": "DICT",
            "dict": "DICT",
            "bool": "BOOLEAN",
            "boolean": "BOOLEAN",
            "path": "FILE_PATH",
            "file_path": "FILE_PATH",
            "filepath": "FILE_PATH",
        }

        rendered: List[str] = []
        for p in params:
            if not isinstance(p, dict):
                continue
            name = str(p.get("name") or "param")
            raw_type = str(p.get("type") or "string").strip().lower()
            p_type = type_mapping.get(raw_type, raw_type.upper())
            if p_type not in {"STRING", "INTEGER", "BOOLEAN", "LIST", "DICT", "FILE_PATH"}:
                p_type = "STRING"
            desc = str(p.get("description") or f"{name} parameter")
            req = bool(p.get("required", True))
            rendered.append(
                f"Parameter(name={json.dumps(name)}, type=ParameterType.{p_type}, description={json.dumps(desc)}, required={str(req)})"
            )
        return rendered

    def _safe_capability_name(self, name: Optional[str]) -> str:
        value = str(name or "execute")
        cleaned = "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in value)
        cleaned = cleaned.strip("_") or "execute"
        if cleaned[0].isdigit():
            cleaned = f"op_{cleaned}"
        return cleaned

    def _safety_level_from_risk(self, risk_level: float) -> str:
        try:
            r = float(risk_level)
        except Exception:
            r = 0.5
        if r >= 0.85:
            return "CRITICAL"
        if r >= 0.65:
            return "HIGH"
        if r >= 0.35:
            return "MEDIUM"
        return "LOW"
    
    def _generate_stage2_handlers(self, skeleton: str, prompt_spec: dict, tool_spec: dict, contract: str) -> Optional[str]:
        """Stage 2: implement handlers.

        Simple tools (<=COMPLEXITY_THRESHOLD handlers): one-shot call.
        Complex tools: sequential — one handler at a time, each call sees the
        growing file so implementations stay consistent with each other.
        """
        from core.tool_creation.code_generator.base import COMPLEXITY_THRESHOLD
        handler_names = self._extract_handler_names(skeleton, tool_spec)

        if not handler_names:
            logger.warning("No handlers found in skeleton")
            return skeleton

        if len(handler_names) <= COMPLEXITY_THRESHOLD:
            logger.info(f"Simple tool ({len(handler_names)} handlers) — one-shot generation")
            result = self._generate_all_handlers(skeleton, handler_names, prompt_spec, tool_spec, contract)
            # Fall back to sequential if one-shot returns empty
            if not result:
                logger.warning("One-shot returned empty — falling back to sequential")
                return self._generate_handlers_sequentially(skeleton, handler_names, prompt_spec, tool_spec, contract)
            return result
        else:
            logger.info(f"Complex tool ({len(handler_names)} handlers > {COMPLEXITY_THRESHOLD}) — sequential generation")
            return self._generate_handlers_sequentially(skeleton, handler_names, prompt_spec, tool_spec, contract)
    
    def _extract_handler_names(self, code: str, tool_spec: dict) -> List[str]:
        """Extract handler method names from skeleton"""
        try:
            tree = ast.parse(code)
        except:
            return []
        
        class_name = self._class_name(tool_spec["name"])
        class_node = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name), None)
        if not class_node:
            return []
        
        handlers = []
        for node in class_node.body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith('_handle_'):
                handlers.append(node.name)
        
        return handlers
    
    def _generate_all_handlers(self, skeleton: str, handler_names: List[str], prompt_spec: dict, tool_spec: dict, contract: str) -> Optional[str]:
        """Generate all handler implementations in a single LLM call."""
        skill_guidance = self._build_skill_guidance(tool_spec)

        # Build stubs block — show all handlers the LLM needs to implement with full op context
        stubs_block = ""
        for name in handler_names:
            op_name = name.replace('_handle_', '')
            op_spec = next((op for op in (prompt_spec.get("inputs") or [])
                           if isinstance(op, dict) and self._safe_capability_name(op.get("operation")) == op_name), {})
            params_desc = ", ".join(
                p.get("name", "") + ("(required)" if p.get("required") else "(optional)")
                for p in (op_spec.get("parameters") or [])
            )
            param_details = "\n".join(
                f"  - {p.get('name')}: {p.get('type','string')} — {p.get('description','')}"
                for p in (op_spec.get("parameters") or []) if isinstance(p, dict)
            )
            stub = self._extract_handler_stub(skeleton, name)
            stubs_block += f"# Operation: {op_name}  params: {params_desc or 'see kwargs'}\n"
            if param_details:
                stubs_block += f"# Parameter details:\n{param_details}\n"
            # Inject sketch if available
            sketch_steps = (tool_spec.get('handler_sketches') or {}).get(name, [])
            if sketch_steps:
                stubs_block += "# Implementation steps:\n"
                for step in sketch_steps:
                    stubs_block += f"#   {step}\n"
            stubs_block += f"{stub}\n\n"

        prompt = f"""Implement ALL handler methods below for a CUA tool. Output ONLY the implemented methods, no class wrapper, no imports.

SKILL CONTEXT:
{skill_guidance}

For each method:
- Use ONLY self.services.* from the contract.
- Return a plain dict with a 'success' key.
- Validate required inputs, return {{'success': False, 'error': '...'}} on bad input.
- NO imports, NO class definition.

Contract:
{contract}

Methods to implement:
{stubs_block}"""

        from core.tool_creation.validator import ToolValidator
        validator = ToolValidator()

        for attempt in range(2):
            raw = self.llm_client._call_llm(prompt, temperature=0.15 if attempt == 0 else 0.1, max_tokens=3000, expect_json=False)
            if not raw or len(raw.strip()) < 50:
                continue

            # Splice each handler found in the response into the skeleton
            code = skeleton
            spliced = 0
            for name in handler_names:
                handler_code = self._extract_handler_method(raw, name)
                if handler_code:
                    code = self._splice_handler_into_code(code, name, handler_code)
                    spliced += 1

            if spliced == 0:
                logger.warning(f"Attempt {attempt+1}: no handlers found in LLM response")
                continue

            if spliced < len(handler_names):
                logger.warning(f"Attempt {attempt+1}: only {spliced}/{len(handler_names)} handlers found")

            ok, err = validator.validate(code, tool_spec)
            if ok:
                logger.info(f"All-handlers generation succeeded ({spliced}/{len(handler_names)} implemented)")
                return code

            logger.warning(f"Attempt {attempt+1} validation failed: {err}")
            # Narrow the prompt on retry to just fix the contract violation
            prompt = prompt + f"\n\nPrevious attempt failed validation: {err}\nFix by using ONLY the allowed self.services.* methods listed in the contract."

        return None

    def _parse_edit_block(self, text: str, handler_name: str) -> Optional[str]:
        """Extract the UPDATED section from an aider-style edit block."""
        # Strip markdown fences first
        if '```' in text:
            text = self._extract_python_code(text)
        
        orig_marker = '<<<< ORIGINAL'
        end_marker = '>>>>'
        # Accept both 7-char (aider standard) and 4-char separators
        sep_marker = '======='
        
        orig_pos = text.find(orig_marker)
        sep_pos = text.find(sep_marker, orig_pos + 1 if orig_pos >= 0 else 0)
        if sep_pos < 0:
            sep_marker = '===='
            sep_pos = text.find(sep_marker, orig_pos + 1 if orig_pos >= 0 else 0)
        end_pos = text.find(end_marker, sep_pos + 1 if sep_pos >= 0 else 0)
        
        if orig_pos < 0 or sep_pos < 0 or end_pos < 0:
            return None
        
        updated = text[sep_pos + len(sep_marker):end_pos].strip()
        if not updated or f'def {handler_name}' not in updated:
            return None
        
        # Re-extract just the method in case there's trailing text
        return self._extract_handler_method(updated, handler_name) or updated

    def _generate_handlers_sequentially(
        self,
        skeleton: str,
        handler_names: List[str],
        prompt_spec: dict,
        tool_spec: dict,
        contract: str,
    ) -> Optional[str]:
        """Generate handlers one at a time.

        Each call receives:
        - The current state of the file (already-implemented handlers visible)
        - Rich per-handler context (purpose, skill, sibling summaries, param contract)
        - The contract

        Falls back to the stub for any handler the LLM fails to produce.
        Returns None only if zero handlers were implemented.
        """
        from core.tool_creation.validator import ToolValidator
        from core.tool_creation.code_generator.base import build_handler_context
        validator = ToolValidator()

        tool_purpose = (
            tool_spec.get("gap_description")
            or tool_spec.get("domain")
            or tool_spec.get("name", "")
        )
        skill_name = tool_spec.get("target_skill") or tool_spec.get("target_category") or ""
        verification_mode = tool_spec.get("verification_mode") or ""

        current_code = skeleton
        implemented: List[str] = []
        failed: List[str] = []

        for handler_name in handler_names:
            op_name = handler_name.replace("_handle_", "")
            op_spec = next(
                (op for op in (prompt_spec.get("inputs") or [])
                 if isinstance(op, dict) and self._safe_capability_name(op.get("operation")) == op_name),
                {}
            )

            handler_context = build_handler_context(
                handler_name=handler_name,
                current_file=current_code,
                tool_purpose=tool_purpose,
                skill_name=skill_name,
                verification_mode=verification_mode,
                op_spec=op_spec,
                already_implemented=implemented,
            )

            # Inject sketch if available
            sketch_steps = (tool_spec.get('handler_sketches') or {}).get(handler_name, [])
            sketch_section = ""
            if sketch_steps:
                sketch_section = "\nIMPLEMENTATION STEPS (follow these exactly):\n" + "\n".join(sketch_steps) + "\n"

            stub = self._extract_handler_stub(current_code, handler_name)

            prompt = f"""Implement ONE handler method for a CUA tool.
Output ONLY the method definition — no class wrapper, no imports.

{handler_context}
{sketch_section}
Current file state (for context — do NOT repeat it, only output the new method):
```python
{current_code}
```

Contract:
{contract}

Method to implement (replace the stub body with real logic):
{stub}

Requirements:
- Use ONLY self.services.* from the contract
- Return {{'success': True, 'data': ...}} or {{'success': False, 'error': '...'}}
- Validate required inputs
- Keep under 25 lines
- NO imports, NO class definition"""

            success = False
            feedback = ""
            for attempt in range(2):
                full_prompt = prompt + (f"\n\nPrevious attempt feedback: {feedback}" if feedback else "")
                raw = self.llm_client._call_llm(
                    full_prompt,
                    temperature=0.15 if attempt == 0 else 0.1,
                    max_tokens=800,
                    expect_json=False,
                )
                if not raw or len(raw.strip()) < 20:
                    feedback = "Output was empty. Return only the method definition."
                    continue

                handler_code = self._extract_handler_method(raw, handler_name)
                if not handler_code:
                    feedback = f"Output did not contain def {handler_name}. Return only the method."
                    continue

                candidate = self._splice_handler_into_code(current_code, handler_name, handler_code)
                ok, err = validator.validate(candidate, tool_spec)
                if ok:
                    current_code = candidate
                    implemented.append(handler_name)
                    logger.info(f"Sequential: implemented {handler_name} ({len(implemented)}/{len(handler_names)})")
                    success = True
                    break
                feedback = f"Validation failed: {err}. Fix and return only the method."

            if not success:
                logger.warning(f"Sequential: failed to implement {handler_name}, keeping stub")
                failed.append(handler_name)

        if not implemented:
            logger.error("Sequential generation: zero handlers implemented")
            return None

        if failed:
            logger.warning(f"Sequential generation: {len(failed)} handlers kept as stubs: {failed}")

        return current_code

    def _extract_handler_stub(self, code: str, handler_name: str) -> str:
        """Extract just the stub method lines for a given handler."""
        lines = code.splitlines()
        result = []
        inside = False
        base_indent = None
        for line in lines:
            if not inside:
                stripped = line.lstrip()
                if stripped.startswith(f"def {handler_name}("):
                    inside = True
                    base_indent = len(line) - len(stripped)
                    result.append(line)
            else:
                current_indent = len(line) - len(line.lstrip()) if line.strip() else base_indent + 4
                if line.strip() and current_indent <= base_indent:
                    break
                result.append(line)
        return "\n".join(result) if result else f"    def {handler_name}(self, **kwargs):\n        pass"

    def _extract_handler_method(self, text: str, handler_name: str) -> Optional[str]:
        """Extract just the handler method from LLM output (strips markdown, class wrapper, etc)."""
        # Strip markdown code fences
        if '```python' in text:
            text = text[text.find('```python') + 9:]
            text = text[:text.find('```')] if '```' in text else text
        elif '```' in text:
            text = text[text.find('```') + 3:]
            text = text[:text.find('```')] if '```' in text else text
        text = text.strip()

        lines = text.splitlines()
        result = []
        inside = False
        base_indent = None
        for line in lines:
            if not inside:
                stripped = line.lstrip()
                if stripped.startswith(f"def {handler_name}("):
                    inside = True
                    base_indent = len(line) - len(stripped)
                    result.append(line)
            else:
                current_indent = len(line) - len(line.lstrip()) if line.strip() else base_indent + 4
                if line.strip() and current_indent <= base_indent:
                    break
                result.append(line)
        return "\n".join(result) if result else None

    def _splice_handler_into_code(self, code: str, handler_name: str, new_handler: str) -> str:
        """Replace the stub handler in code with the new implementation."""
        lines = code.splitlines()
        result = []
        inside = False
        base_indent = None
        skipping = False
        for line in lines:
            if not inside and not skipping:
                stripped = line.lstrip()
                if stripped.startswith(f"def {handler_name}("):
                    inside = True
                    base_indent = len(line) - len(stripped)
                    # Inject new handler (re-indent to match original)
                    for new_line in new_handler.splitlines():
                        new_stripped = new_line.lstrip()
                        new_indent = len(new_line) - len(new_stripped) if new_line.strip() else 0
                        result.append(" " * (base_indent + new_indent) + new_stripped if new_line.strip() else "")
                    skipping = True
                else:
                    result.append(line)
            elif skipping:
                current_indent = len(line) - len(line.lstrip()) if line.strip() else base_indent + 4
                if line.strip() and current_indent <= base_indent:
                    skipping = False
                    inside = False
                    result.append(line)
            else:
                result.append(line)
        return "\n".join(result) + "\n"

    def _extract_python_code(self, text: str) -> str:
        """Extract Python code from LLM response"""
        if '```python' in text:
            start = text.find('```python') + 9
            end = text.find('```', start)
            return text[start:end].strip()
        elif '```' in text:
            start = text.find('```') + 3
            end = text.find('```', start)
            return text[start:end].strip()
        return text.strip()
    
    def _class_name(self, tool_name: str) -> str:
        from core.tool_creation.code_generator.base import canonical_class_name
        return canonical_class_name(tool_name)
    
    def _build_prompt_spec(self, tool_spec: dict) -> dict:
        """Build prompt specification from tool spec — preserve all skill/gap context."""
        return {
            "name": tool_spec.get("name", "UnknownTool"),
            "domain": tool_spec.get("domain", tool_spec.get("description", "general")),
            "inputs": tool_spec.get("inputs", tool_spec.get("capabilities", [])),
            "outputs": tool_spec.get("outputs", []),
            "dependencies": tool_spec.get("dependencies", []),
            "risk_level": tool_spec.get("risk_level", 0.5),
            "target_skill": tool_spec.get("target_skill"),
            "target_category": tool_spec.get("target_category"),
            "verification_mode": tool_spec.get("verification_mode"),
            "example_tasks": tool_spec.get("example_tasks", []),
            "example_errors": tool_spec.get("example_errors", []),
            "gap_type": tool_spec.get("gap_type"),
        }
    
    def _build_contract_pack(self, skill_category: str = None) -> str:
        """Build contract documentation, optionally filtered to skill-relevant services."""
        from core.tool_creation.code_generator.base import TOOL_CREATION_RULES
        SKILL_SERVICES = {
            "web":         {"http", "storage", "json", "logging", "ids"},
            "computer":    {"fs", "shell", "storage", "logging", "ids"},
            "development": {"fs", "shell", "storage", "json", "logging", "ids"},
            "automation":  {"storage", "http", "logging", "ids", "time"},
            "data":        {"json", "storage", "logging", "ids", "llm", "fs"},
            "productivity":{"storage", "json", "logging", "ids", "time"},
        }
        try:
            from core.enhanced_code_validator import EnhancedCodeValidator
            service_registry = EnhancedCodeValidator().service_registry or {}
        except Exception:
            service_registry = {}

        lines = [
            TOOL_CREATION_RULES,
            "CUA Tool Contract (strict):",
            "- Tools inherit from tools.tool_interface.BaseTool",
            "- register_capabilities(): MUST use self.add_capability(capability, handler_func)",
            "- execute(self, operation: str, **kwargs): MUST use return self.execute_capability(operation, **kwargs)",
            "- Handler methods MUST return {'success': True/False, 'data'/'error': ...}",
            "",
            "ToolServices usage rules:",
            "- Only call methods on self.services that are explicitly listed below.",
            "- DO NOT invent or assume new self.services.* methods.",
            "- If you need persistence, use storage.save/get/list/find/update/delete/exists.",
            "",
            "IMPORTANT - Storage Service Usage:",
            "- storage is a KEY-VALUE store, NOT a collection store",
            "- save(id, data): saves ONE item with unique ID (use self.services.ids.uuid() for IDs)",
            "- get(id): retrieves ONE item by ID",
            "- list(limit=10): returns ALL items (no filtering)",
            "- delete(id): deletes ONE item by ID",
            "- For collections: use unique IDs like 'benchmark_case_<uuid>' and list() to get all",
            "",
            "Allowed self.services methods:",
        ]

        if service_registry:
            allowed = SKILL_SERVICES.get(skill_category) if skill_category else None
            for svc_name in sorted(service_registry.keys()):
                if allowed and svc_name not in allowed:
                    continue
                methods = service_registry.get(svc_name) or []
                if not methods:
                    continue
                lines.append(f"- self.services.{svc_name}: {', '.join(sorted(set(methods)))}")
        else:
            allowed = SKILL_SERVICES.get(skill_category) if skill_category else None
            fallback = [
                ("storage", "save, get, list, find, count, update, delete, exists"),
                ("llm",     "generate"),
                ("http",    "get, post, put, delete"),
                ("fs",      "read, write, list"),
                ("json",    "parse, stringify, query"),
                ("shell",   "execute"),
                ("time",    "now_utc, now_local, now_utc_iso, now_local_iso"),
                ("ids",     "generate, uuid"),
                ("logging", "info, warning, error, debug"),
            ]
            for svc_name, methods in fallback:
                if allowed and svc_name not in allowed:
                    continue
                lines.append(f"- self.services.{svc_name}: {methods}")

        lines.extend(
            [
                "",
                "Error handling rules:",
                "- Prefer returning {'success': False, 'error': '...', 'data': None} instead of raising exceptions.",
                "- Validate required inputs.",
            ]
        )
        return "\n".join(lines) + "\n"
    
    def _build_skill_guidance(self, tool_spec: dict) -> str:
        """Build skill-specific implementation guidance by reading actual skill.json."""
        target_skill = tool_spec.get("target_skill")
        target_category = tool_spec.get("target_category", "general")

        # Try to load actual skill.json for rich context
        skill_data = {}
        if target_skill:
            try:
                from pathlib import Path
                import json as _json
                skill_file = Path(f"skills/{target_skill}/skill.json")
                if skill_file.exists():
                    skill_data = _json.loads(skill_file.read_text())
            except Exception:
                pass

        lines = [f"Target Skill: {target_skill or 'unknown'}", f"Target Category: {target_category}"]

        if skill_data:
            if skill_data.get("description"):
                lines.append(f"Skill Purpose: {skill_data['description']}")
            preferred = skill_data.get("preferred_tools") or []
            if preferred:
                lines.append(f"Preferred tools in this skill: {', '.join(preferred)}")
            verification = skill_data.get("verification_mode")
            if verification:
                lines.append(f"Verification mode: {verification}")
                if verification == "source_backed":
                    lines.append("  → Tool MUST return sources/citations in output")
                elif verification == "side_effect_observed":
                    lines.append("  → Tool MUST demonstrate observable side effects")
            risk = skill_data.get("risk_level")
            if risk:
                lines.append(f"Skill risk level: {risk}")
            triggers = skill_data.get("trigger_examples") or skill_data.get("triggers") or []
            if triggers:
                lines.append("This skill handles requests like:")
                for t in triggers[:5]:
                    lines.append(f"  - {t}")
        else:
            # Fallback domain hints
            domain_hints = {
                "web": "Use self.services.http for web requests. Return structured data with sources.",
                "computer": "Use self.services.fs and self.services.shell for local operations only.",
                "development": "Use self.services.fs for code file operations. No external API calls.",
                "data": "Operate on data passed as parameters. Use self.services.json for serialization.",
                "automation": "Use self.services.storage and self.services.http. Track state.",
                "productivity": "Use self.services.storage and self.services.ids for persistence.",
            }
            hint = domain_hints.get(target_category, "Use appropriate self.services.* methods. No hardcoded values.")
            lines.append(hint)

        # Inject example tasks and errors from spec if available
        example_tasks = tool_spec.get("example_tasks") or []
        if example_tasks:
            lines.append("Example tasks this tool should handle:")
            for t in example_tasks[:3]:
                lines.append(f"  - {t}")
        example_errors = tool_spec.get("example_errors") or []
        if example_errors:
            lines.append("Known failure patterns to avoid:")
            for e in example_errors[:3]:
                lines.append(f"  - {e}")

        return "\n".join(lines) + "\n"
