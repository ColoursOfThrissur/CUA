"""
PendingToolsManager - Manages tools awaiting user approval
"""
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path
import json
import logging
from uuid import uuid4

logger = logging.getLogger(__name__)

class PendingToolsManager:
    def __init__(self):
        self.pending_tools = {}  # {tool_id: tool_metadata}
        self.tool_history = []
        self.storage_path = Path("data/pending_tools.json")
        self._load_from_disk()
    
    def add_pending_tool(self, tool_metadata: Dict) -> str:
        """Add tool to pending queue"""
        self._load_from_disk()
        valid, error = self.validate_tool_metadata(tool_metadata)
        if not valid:
            raise ValueError(error)

        tool_id = f"tool_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{uuid4().hex[:6]}"
        
        # Detect if new tool or update (allow explicit override from creator flow)
        if 'is_new_tool' in tool_metadata:
            is_new = bool(tool_metadata.get('is_new_tool'))
        else:
            tool_file = tool_metadata.get('tool_file', '')
            is_new = not Path(tool_file).exists() if tool_file else True
        
        self.pending_tools[tool_id] = {
            **tool_metadata,
            'tool_id': tool_id,
            'status': 'pending',
            'type': 'new_tool' if is_new else 'tool_update',
            'created_at': datetime.now().isoformat(),
            'approved_at': None
        }
        
        self._save_to_disk()
        return tool_id

    def validate_tool_metadata(self, tool_metadata: Dict) -> tuple[bool, str]:
        """Validate required metadata contract for user-added tools."""
        required = ["tool_file", "description"]
        for field in required:
            if not tool_metadata.get(field):
                return False, f"Missing required field: {field}"
        tool_file = str(tool_metadata.get("tool_file", ""))
        if not tool_file.endswith(".py"):
            return False, "tool_file must be a Python file"
        return True, ""

    def validate_tool_file_contract(self, tool_file: str) -> tuple[bool, str]:
        """Validate basic tool contract before activation."""
        p = Path(tool_file)
        if not p.exists():
            return False, f"Tool file not found: {tool_file}"
        try:
            import ast
            content = p.read_text(encoding="utf-8")
            tree = ast.parse(content)
        except Exception as e:
            return False, f"Invalid Python file: {e}"

        classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        if not classes:
            return False, "No class definition found in tool file"
        has_execute = any(
            isinstance(n, ast.FunctionDef) and n.name == "execute"
            for n in ast.walk(tree)
        )
        if not has_execute:
            return False, "Tool must implement execute()"

        register_methods = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "register_capabilities"
        ]
        if not register_methods:
            return False, "Tool must implement register_capabilities()"
        register_method = register_methods[0]
        has_add_capability = any(
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "add_capability"
            for n in ast.walk(register_method)
        )
        if not has_add_capability:
            return False, "register_capabilities() must use add_capability(...)"

        target_class = classes[0]
        class_methods = {
            n.name for n in target_class.body if isinstance(n, ast.FunctionDef)
        }

        # Extract capability parameter contracts to catch handler drift.
        capability_contract = {}
        for node in ast.walk(register_method):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "ToolCapability"):
                continue
            cap_name = None
            params = []
            required = []
            for kw in node.keywords:
                if kw.arg == "name" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
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
                capability_contract[cap_name] = {"parameters": params, "required": required}

        # Guard against undefined private helper calls (common staged-generation drift).
        for method in [n for n in target_class.body if isinstance(n, ast.FunctionDef)]:
            # Guard against invalid isinstance(..., ParameterType.X) usage.
            for call in [n for n in ast.walk(method) if isinstance(n, ast.Call)]:
                if not (isinstance(call.func, ast.Name) and call.func.id == "isinstance"):
                    continue
                if len(call.args) < 2:
                    continue
                second = call.args[1]
                if (
                    isinstance(second, ast.Attribute)
                    and isinstance(second.value, ast.Name)
                    and second.value.id == "ParameterType"
                ):
                    return False, (
                        f"Method '{method.name}' uses isinstance(..., ParameterType.{second.attr}); "
                        "use Python runtime types instead"
                    )

            for call in [n for n in ast.walk(method) if isinstance(n, ast.Call)]:
                if not isinstance(call.func, ast.Attribute):
                    continue
                if not isinstance(call.func.value, ast.Name) or call.func.value.id != "self":
                    continue
                called = call.func.attr
                if not called.startswith("_") or called.startswith("__"):
                    continue
                if called in class_methods:
                    continue
                return False, f"Method '{method.name}' calls undefined helper '{called}'"

        # REMOVED: Overly strict handler parameter validation
        # Thin tools with TODO stubs don't need to reference all params yet
        # The orchestrator validates parameters at runtime from ToolCapability

        def _path_text(node):
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

        def _data_root(path_text: str):
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

        def _collect_roots(fn_node):
            roots = set()
            for call in [n for n in ast.walk(fn_node) if isinstance(n, ast.Call)]:
                if not isinstance(call.func, ast.Name) or call.func.id != "open":
                    continue
                if not call.args:
                    continue
                text = _path_text(call.args[0])
                if not text:
                    continue
                root = _data_root(text)
                if root:
                    roots.add(root)
            return roots

        def _open_mode(call):
            if len(call.args) >= 2 and isinstance(call.args[1], ast.Constant) and isinstance(call.args[1].value, str):
                return call.args[1].value
            for kw in call.keywords:
                if kw.arg == "mode" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    return kw.value.value
            return "r"

        def _has_true_exist_ok(call):
            for kw in call.keywords:
                if kw.arg == "exist_ok" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                    return True
            return False

        def _has_dir_prepare(fn_node):
            for call in [n for n in ast.walk(fn_node) if isinstance(n, ast.Call)]:
                if isinstance(call.func, ast.Attribute):
                    if isinstance(call.func.value, ast.Name) and call.func.value.id == "os" and call.func.attr == "makedirs":
                        if _has_true_exist_ok(call):
                            return True
                    if call.func.attr == "mkdir" and _has_true_exist_ok(call):
                        return True
            return False

        for method in [n for n in target_class.body if isinstance(n, ast.FunctionDef)]:
            writes_to_data = False
            for call in [n for n in ast.walk(method) if isinstance(n, ast.Call)]:
                if not isinstance(call.func, ast.Name) or call.func.id != "open":
                    continue
                if not call.args:
                    continue
                text = _path_text(call.args[0])
                if not text or "data/" not in text.replace("\\", "/"):
                    continue
                mode = _open_mode(call)
                if any(flag in mode for flag in ("w", "a", "x")):
                    writes_to_data = True
                    break
            if writes_to_data and not _has_dir_prepare(method):
                return False, f"Method '{method.name}' writes under data/ but does not create directories first"

        create_method = next((n for n in target_class.body if isinstance(n, ast.FunctionDef) and n.name == "_handle_create"), None)
        get_method = next((n for n in target_class.body if isinstance(n, ast.FunctionDef) and n.name == "_handle_get"), None)
        if create_method and get_method:
            create_roots = _collect_roots(create_method)
            get_roots = _collect_roots(get_method)
            if create_roots and get_roots and create_roots.isdisjoint(get_roots):
                return False, "Storage path mismatch between _handle_create and _handle_get"
        return True, ""
    
    def approve_tool(self, tool_id: str) -> Dict:
        """Mark tool as approved"""
        self._load_from_disk()
        if tool_id not in self.pending_tools:
            return {'success': False, 'error': 'Tool not found'}
        
        tool = self.pending_tools[tool_id]
        tool['status'] = 'approved'
        tool['approved_at'] = datetime.now().isoformat()
        
        self.tool_history.append(tool)
        del self.pending_tools[tool_id]
        
        self._save_to_disk()
        return {'success': True, 'tool': tool}
    
    def reject_tool(self, tool_id: str, reason: str = '') -> Dict:
        """Reject and remove tool"""
        self._load_from_disk()
        if tool_id not in self.pending_tools:
            return {'success': False, 'error': 'Tool not found'}
        
        tool = self.pending_tools[tool_id]
        tool['status'] = 'rejected'
        tool['rejection_reason'] = reason
        
        # Clean up generated files if they exist
        tool_file = tool.get('tool_file')
        test_file = tool.get('test_file')
        
        if tool_file and Path(tool_file).exists():
            try:
                Path(tool_file).unlink()
            except Exception as e:
                logger.warning("Failed to delete rejected tool file %s: %s", tool_file, e)
        if test_file and Path(test_file).exists():
            try:
                Path(test_file).unlink()
            except Exception as e:
                logger.warning("Failed to delete rejected tool test file %s: %s", test_file, e)
        
        del self.pending_tools[tool_id]
        self._save_to_disk()
        
        return {'success': True}
    
    def get_pending_list(self) -> List[Dict]:
        """Get all pending tools"""
        try:
            if self.storage_path.exists():
                data = self._normalize_storage(json.loads(self.storage_path.read_text()))
                pending = data.get('pending', {})
                self.pending_tools = pending
                self.tool_history = data.get('history', [])
                return list(pending.values())
        except Exception as e:
            logger.warning("Failed reading pending tools list from %s: %s", self.storage_path, e)
        return list(self.pending_tools.values())

    def get_history(self) -> List[Dict]:
        """Get approved/rejected tool history."""
        try:
            if self.storage_path.exists():
                data = self._normalize_storage(json.loads(self.storage_path.read_text()))
                self.pending_tools = data.get('pending', {})
                self.tool_history = data.get('history', [])
                return list(self.tool_history)
        except Exception as e:
            logger.warning("Failed reading pending tools history from %s: %s", self.storage_path, e)
        return list(self.tool_history)
    
    def get_tool(self, tool_id: str) -> Optional[Dict]:
        """Get specific tool metadata"""
        try:
            if self.storage_path.exists():
                data = json.loads(self.storage_path.read_text())
                pending = data.get('pending', {})
                self.pending_tools = pending
                return pending.get(tool_id)
        except Exception as e:
            logger.warning("Failed reading pending tool %s from %s: %s", tool_id, self.storage_path, e)
        return self.pending_tools.get(tool_id)
    
    def _save_to_disk(self):
        """Persist to disk"""
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                'pending': self.pending_tools,
                'history': self.tool_history[-50:]  # Keep last 50
            }
            self.storage_path.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.warning("Failed saving pending tools to %s: %s", self.storage_path, e)
    
    def _load_from_disk(self):
        """Load from disk"""
        try:
            if self.storage_path.exists():
                data = self._normalize_storage(json.loads(self.storage_path.read_text()))
                self.pending_tools = data.get('pending', {})
                self.tool_history = data.get('history', [])
        except Exception as e:
            logger.warning("Failed loading pending tools from %s: %s", self.storage_path, e)

    def _normalize_storage(self, raw) -> Dict:
        """Normalize legacy storage formats."""
        if isinstance(raw, dict):
            pending = raw.get('pending', {})
            history = raw.get('history', [])
            if isinstance(pending, list):
                pending = {
                    item.get('tool_id', f"legacy_{index}"): item
                    for index, item in enumerate(pending)
                    if isinstance(item, dict)
                }
            if not isinstance(pending, dict):
                pending = {}
            if not isinstance(history, list):
                history = []
            return {'pending': pending, 'history': history}

        if isinstance(raw, list):
            pending = {}
            history = []
            for index, item in enumerate(raw):
                if not isinstance(item, dict):
                    continue
                status = item.get('status', 'pending')
                tool_id = item.get('tool_id', f"legacy_{index}")
                if status == 'pending':
                    pending[tool_id] = item
                else:
                    history.append(item)
            return {'pending': pending, 'history': history}

        return {'pending': {}, 'history': []}
