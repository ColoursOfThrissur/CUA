"""
Base code generator interface + shared context utilities used by both
creation (qwen_generator) and evolution (code_generator) pipelines.
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
import ast
import re

# ── Structural rules injected into every tool creation prompt ─────────────────
TOOL_CREATION_RULES = """
STRUCTURAL RULES (mandatory — evolution pipeline depends on these):

1. execute() MUST delegate via execute_capability():
   def execute(self, operation: str, **kwargs):
       return self.execute_capability(operation, **kwargs)
   DO NOT write manual if/elif chains in execute(). The capability registry handles routing.

2. Handler return shape MUST always include 'success' key:
   return {'success': True, 'data': <result>}   # on success
   return {'success': False, 'error': '<msg>'}   # on failure
   Never return bare lists, bare strings, or dicts without 'success'.

3. ToolCapability fields MUST use these exact values:
   returns="dict"                    # always the string "dict"
   examples=[]                       # always empty list
   dependencies=[]                   # always empty list (services declared in __init__ only)

4. Parameter types MUST match the value shape:
   - Plural names (datasets, keys, plans, texts, items, ids, steps, results, tags,
     files, paths, queries, methods, workflows, records) -> ParameterType.LIST
   - Count/size names (limit, count, max, min, size, num, number, page, offset,
     timeout, retries, priority) -> ParameterType.INTEGER
   - Everything else -> ParameterType.STRING or ParameterType.DICT as appropriate

5. Inter-tool calls MUST use public capability names only:
   self.services.call_tool('ToolName', 'capability_name', param=value)
   NEVER call private methods (_handle_*) via call_tool.
"""

# Tools with more handlers than this get sequential generation instead of one-shot
COMPLEXITY_THRESHOLD = 5


def canonical_class_name(tool_name: str) -> str:
    """Convert tool_name to ClassName. Preserves existing CamelCase, handles snake_case."""
    name = (tool_name or "").strip()
    if not name:
        return "GeneratedTool"
    # Already CamelCase (no underscores/hyphens, has interior uppercase) — keep stable
    if "_" not in name and "-" not in name and any(ch.isupper() for ch in name[1:]):
        return name[:1].upper() + name[1:]
    parts = [p for p in name.replace("-", "_").split("_") if p]
    return "".join((p[:1].upper() + p[1:]) for p in parts)


def build_handler_context(
    handler_name: str,
    current_file: str,
    tool_purpose: str,
    skill_name: str,
    verification_mode: str,
    op_spec: Dict[str, Any],
    already_implemented: List[str],
) -> str:
    """Build a rich per-handler context block used by both creation and evolution.

    Gives the LLM:
    - What the tool is for (purpose + skill + verification contract)
    - What this specific handler must do (full param contract with types/required/defaults)
    - What sibling handlers already do (one-liner each from AST — no duplication)
    - Which handlers are already implemented in this session (stay consistent)
    - Storage key pattern already in use (so naming stays consistent)
    """
    lines: List[str] = []

    # Tool purpose block
    lines.append("=== TOOL CONTEXT ===")
    if tool_purpose:
        lines.append(f"Tool purpose: {tool_purpose}")
    if skill_name:
        lines.append(f"Skill: {skill_name}")
    if verification_mode:
        lines.append(f"Verification mode: {verification_mode}")
        if verification_mode == "source_backed":
            lines.append("  -> Every handler that fetches data MUST include 'sources' in its return dict")
        elif verification_mode == "side_effect_observed":
            lines.append("  -> Handlers that write/create MUST include 'path' or 'file_path' in return dict")

    # This handler's operation contract
    lines.append(f"\n=== HANDLER TO IMPLEMENT: {handler_name} ===")
    op_name = handler_name.replace("_handle_", "")
    lines.append(f"Operation: {op_name}")
    params = op_spec.get("parameters") or []
    if params:
        lines.append("Parameters (extract from kwargs):")
        for p in params:
            if not isinstance(p, dict):
                continue
            req = "REQUIRED" if p.get("required", True) else f"optional, default={p.get('default', 'None')}"
            lines.append(f"  - {p.get('name')}: {p.get('type', 'string')} ({req}) -- {p.get('description', '')}")
    else:
        lines.append("Parameters: none (stateless operation)")
    expected_out = op_spec.get("expected_output") or op_spec.get("returns") or ""
    if expected_out and expected_out != "dict":
        lines.append(f"Expected output shape: {expected_out}")

    # Sibling handlers already in the file
    sibling_summaries = _extract_sibling_summaries(current_file, handler_name)
    if sibling_summaries:
        lines.append("\n=== SIBLING HANDLERS (already in file -- do NOT duplicate their logic) ===")
        for name, summary in sibling_summaries.items():
            lines.append(f"  {name}: {summary}")

    # Already-implemented handlers in this session
    if already_implemented:
        lines.append(f"\nAlready implemented this session: {', '.join(already_implemented)}")
        lines.append("Their implementations are visible in the current file -- stay consistent.")

    # Storage key pattern
    storage_pattern = _extract_storage_key_pattern(current_file)
    if storage_pattern:
        lines.append(f"\nStorage key pattern already in use: {storage_pattern}")
        lines.append("Use the same pattern for any new storage.save/get calls.")

    return "\n".join(lines)


def _extract_sibling_summaries(code: str, exclude_handler: str) -> Dict[str, str]:
    """AST-extract a one-line summary of each sibling handler."""
    summaries: Dict[str, str] = {}
    try:
        tree = ast.parse(code)
        cls = next((n for n in tree.body if isinstance(n, ast.ClassDef)), None)
        if not cls:
            return summaries
        src_lines = code.splitlines()
        for node in cls.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            if not node.name.startswith("_handle_"):
                continue
            if node.name == exclude_handler:
                continue
            body_lines = src_lines[node.lineno: node.end_lineno]
            for bl in body_lines:
                stripped = bl.strip()
                if stripped and not stripped.startswith("#") and stripped != "pass" and "stub" not in stripped:
                    summaries[node.name] = stripped[:100]
                    break
            else:
                summaries[node.name] = "(stub)"
    except Exception:
        pass
    return summaries


def _extract_storage_key_pattern(code: str) -> str:
    """Find the storage key prefix already used in the file."""
    patterns = re.findall(r'ids\.generate\(["\']([^"\'\.]+)["\']\)', code)
    if patterns:
        return f'"{patterns[0]}_<uuid>"'
    patterns = re.findall(r'storage\.save\(["\']([^"\'\.]+)["\']', code)
    if patterns:
        return f'"{patterns[0]}"'
    return ""


class BaseCodeGenerator(ABC):
    """Base interface for tool code generation strategies"""

    def __init__(self, llm_client, flow):
        self.llm_client = llm_client
        self.flow = flow

    @abstractmethod
    def generate(self, template: str, tool_spec: dict) -> Optional[str]:
        """Generate tool code from template and spec"""
        pass
