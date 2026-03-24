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
        contract = self._build_contract_pack()
        
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
        """Stage 2: Implement handlers one by one"""
        code = skeleton
        handler_names = self._extract_handler_names(code, tool_spec)
        
        if not handler_names:
            logger.warning("No handlers found in skeleton")
            return code
        
        for handler_name in handler_names:
            logger.info(f"Generating handler: {handler_name}")
            code = self._generate_single_handler(code, handler_name, prompt_spec, tool_spec, contract)
            if not code:
                logger.error(f"Failed to generate handler: {handler_name}")
                return None
        
        return code
    
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
    
    def _generate_single_handler(self, code: str, handler_name: str, prompt_spec: dict, tool_spec: dict, contract: str) -> Optional[str]:
        """Generate implementation for one handler"""
        op_name = handler_name.replace('_handle_', '')
        
        # Build skill-specific guidance
        skill_guidance = self._build_skill_guidance(tool_spec)
        
        # Extract just the stub body so the LLM only sees and outputs the handler, not the whole file
        handler_stub = self._extract_handler_stub(code, handler_name)
        op_spec = next((op for op in (prompt_spec.get("inputs") or []) if isinstance(op, dict) and self._safe_capability_name(op.get("operation")) == op_name), {})
        params_desc = ", ".join(p.get("name", "") + ("(required)" if p.get("required") else "(optional)") for p in (op_spec.get("parameters") or []))

        prompt = f"""Implement this Python method using the edit block format.

SKILL CONTEXT:
{skill_guidance}

Operation: {op_name}
Parameters: {params_desc or 'see kwargs'}

Edit block format — output EXACTLY this structure, nothing else:
<<<< ORIGINAL
{handler_stub}
=======
<your implementation here>
>>>>

Hard requirements:
- The UPDATED section must be a complete def {handler_name}(self, **kwargs): ... method.
- Use ONLY self.services.* for external interactions.
- Return a plain dict (not ToolResult). Include 'success' key.
- Validate required inputs, return {{'success': False, 'error': '...'}} on bad input.
- DO NOT invent new service methods. Only call methods in the contract.
- DO NOT output imports, class definition, or other methods.

Contract reference:
{contract}
"""
        
        from core.tool_creation.validator import ToolValidator
        validator = ToolValidator()

        # Two-attempt loop: generate then (if needed) retry with explicit validator feedback.
        feedback = ""
        for attempt in range(2):
            full_prompt = f"{prompt}\n\n{feedback}" if feedback else prompt
            raw = self.llm_client._call_llm(full_prompt, temperature=0.15 if attempt == 0 else 0.05, expect_json=False)
            if not raw:
                feedback = "Previous output was empty. Return the edit block."
                continue

            handler_code = self._parse_edit_block(raw, handler_name)
            if not handler_code:
                # Fall back to direct method extraction if LLM ignored the format
                handler_code = self._extract_handler_method(raw, handler_name)
            if not handler_code:
                feedback = (
                    f"Output did not contain a valid edit block or def {handler_name}.\n"
                    f"Use the exact format:\n<<<< ORIGINAL\n{handler_stub}\n=======\n<implementation>\n>>>>"
                )
                continue

            candidate = self._splice_handler_into_code(code, handler_name, handler_code)
            ok, err = validator.validate(candidate, tool_spec)
            if ok:
                return candidate

            err_text = str(err or "")
            if "Unknown method: self.services." in err_text or "CUA validation failed" in err_text:
                feedback = (
                    "Previous output failed contract validation.\n"
                    f"Validation error:\n{err_text}\n\n"
                    "Fix by using ONLY the allowed ToolServices methods listed in the contract reference.\n"
                    "Return only the method definition.\n"
                )
                continue

            return None

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
        """Convert tool name to class name"""
        name = (tool_name or "").strip()
        if not name:
            return "GeneratedTool"

        # If user/spec already provides a CamelCase class-like name, keep it stable.
        # (Python's str.capitalize() would lowercase the rest and break names like UserApprovalGateTool.)
        if ("_" not in name) and ("-" not in name) and any(ch.isupper() for ch in name[1:]):
            return name[:1].upper() + name[1:]

        parts = [p for p in name.replace("-", "_").split("_") if p]
        return "".join((p[:1].upper() + p[1:]) for p in parts)
    
    def _build_prompt_spec(self, tool_spec: dict) -> dict:
        """Build prompt specification from tool spec"""
        return {
            "name": tool_spec.get("name", "UnknownTool"),
            "domain": tool_spec.get("domain", tool_spec.get("description", "general")),
            "inputs": tool_spec.get("inputs", tool_spec.get("capabilities", [])),
            "outputs": tool_spec.get("outputs", []),
            "dependencies": tool_spec.get("dependencies", []),
            "risk_level": tool_spec.get("risk_level", 0.5),
        }
    
    def _build_contract_pack(self) -> str:
        """Build contract documentation"""
        try:
            from core.enhanced_code_validator import EnhancedCodeValidator
            service_registry = EnhancedCodeValidator().service_registry or {}
        except Exception:
            service_registry = {}

        lines = [
            "CUA Tool Contract (strict):",
            "- Tools inherit from tools.tool_interface.BaseTool",
            "- register_capabilities(): MUST use self.add_capability(capability, handler_func)",
            "- execute(self, operation: str, **kwargs): MUST dispatch via BaseTool.execute_capability()",
            "- Handler methods MUST return a plain dict (business payload).",
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
            for svc_name in sorted(service_registry.keys()):
                methods = service_registry.get(svc_name) or []
                if not methods:
                    continue
                lines.append(f"- self.services.{svc_name}: {', '.join(sorted(set(methods)))}")
        else:
            # Safe fallback (matches EnhancedCodeValidator defaults)
            lines.extend(
                [
                    "- self.services.storage: save, get, list, find, count, update, delete, exists",
                    "- self.services.llm: generate",
                    "- self.services.http: get, post, put, delete, request",
                    "- self.services.fs: read, write, list",
                    "- self.services.json: parse, stringify, query",
                    "- self.services.shell: execute",
                    "- self.services.time: now_utc, now_local, now_utc_iso, now_local_iso",
                    "- self.services.ids: generate, uuid",
                    "- self.services.logging: info, warning, error, debug",
                ]
            )

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
        """Build skill-specific implementation guidance"""
        target_skill = tool_spec.get("target_skill")
        target_category = tool_spec.get("target_category", "general")
        
        guidance_map = {
            "web": (
                "Domain: Web Research\n"
                "- Use self.services.http for web requests (get/post methods only)\n"
                "- Store results via self.services.storage\n"
                "- NO hardcoded URLs - all URLs must come from parameters\n"
                "- Return structured data with sources/links\n"
                "- Example: fetch URL from parameter, parse response, store result"
            ),
            "computer": (
                "Domain: Computer Automation (LOCAL operations only)\n"
                "- Use self.services.fs for file operations (read/write/list)\n"
                "- Use self.services.shell for command execution\n"
                "- ALL operations are LOCAL - NO external APIs or network calls\n"
                "- NO hardcoded paths - use parameters\n"
                "- Example: read local file, process content, write result locally"
            ),
            "development": (
                "Domain: Code Workspace\n"
                "- Use self.services.fs for code file operations\n"
                "- Focus on local repository operations\n"
                "- NO external API calls\n"
                "- Example: read code files, analyze, write reports"
            ),
            "data": (
                "Domain: Data Operations (in-memory transformation)\n"
                "- Operate on data passed directly as parameters (list of dicts)\n"
                "- Use self.services.json for serialization if needed\n"
                "- Use self.services.storage to persist results if needed\n"
                "- NO external HTTP calls unless the operation explicitly fetches data\n"
                "- NO filesystem access\n"
                "- Return transformed data directly in the result dict"
            ),
            "general": (
                "Domain: General\n"
                "- Use appropriate self.services.* methods\n"
                "- Avoid external dependencies\n"
                "- NO hardcoded values - use parameters\n"
                "- Keep operations simple and deterministic"
            )
        }
        
        guidance = guidance_map.get(target_category, guidance_map["general"])
        
        return f"""Target Skill: {target_skill or 'unknown'}
Target Category: {target_category}

{guidance}
"""
