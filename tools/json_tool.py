"""
JSON Tool - Full JSON manipulation: parse, stringify, query, merge, filter, transform, diff.
"""
import json

from tools.tool_interface import BaseTool
from tools.tool_result import ToolResult, ResultStatus
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel


class JSONTool(BaseTool):

    def __init__(self, orchestrator=None):
        self.description = "Parse, query, transform, merge, filter, and diff JSON data."
        super().__init__()
        if orchestrator:
            self.services = orchestrator.get_services(self.__class__.__name__)

    def register_capabilities(self):
        self.add_capability(ToolCapability(
            name="parse",
            description="Parse a JSON string into a Python object.",
            parameters=[Parameter("text", ParameterType.STRING, "JSON string to parse")],
            returns="Parsed object.",
            safety_level=SafetyLevel.LOW,
            examples=[{"text": "{\"key\": \"value\"}"}],
        ), self._handle_parse)

        self.add_capability(ToolCapability(
            name="stringify",
            description="Serialize a Python object to a JSON string.",
            parameters=[
                Parameter("data", ParameterType.DICT, "Data to serialize"),
                Parameter("indent", ParameterType.INTEGER, "Indent spaces. Default: 2", required=False),
                Parameter("sort_keys", ParameterType.BOOLEAN, "Sort keys alphabetically. Default: false", required=False),
            ],
            returns="JSON string.",
            safety_level=SafetyLevel.LOW,
            examples=[{"data": {"key": "value"}}],
        ), self._handle_stringify)

        self.add_capability(ToolCapability(
            name="query",
            description="Extract a value from a JSON object using a dot-separated path. Supports array index: user.addresses.0.city",
            parameters=[
                Parameter("data", ParameterType.DICT, "JSON object to query"),
                Parameter("path", ParameterType.STRING, "Dot-separated key path, e.g. user.name or items.0.id"),
            ],
            returns="Value at the given path.",
            safety_level=SafetyLevel.LOW,
            examples=[{"data": {"user": {"name": "Alice"}}, "path": "user.name"}],
        ), self._handle_query)

        self.add_capability(ToolCapability(
            name="merge",
            description="Deep-merge two JSON objects. Values in 'override' take precedence over 'base'.",
            parameters=[
                Parameter("base", ParameterType.DICT, "Base object"),
                Parameter("override", ParameterType.DICT, "Object whose values override base"),
            ],
            returns="Merged object.",
            safety_level=SafetyLevel.LOW,
            examples=[{"base": {"a": 1, "b": 2}, "override": {"b": 99, "c": 3}}],
        ), self._handle_merge)

        self.add_capability(ToolCapability(
            name="flatten",
            description="Flatten a nested JSON object into a single-level dict with dot-separated keys.",
            parameters=[
                Parameter("data", ParameterType.DICT, "Nested object to flatten"),
                Parameter("separator", ParameterType.STRING, "Key separator. Default: .", required=False),
            ],
            returns="Flat dict.",
            safety_level=SafetyLevel.LOW,
            examples=[{"data": {"a": {"b": {"c": 1}}}}],
        ), self._handle_flatten)

        self.add_capability(ToolCapability(
            name="filter_array",
            description="Filter a JSON array keeping only items where a field matches a value.",
            parameters=[
                Parameter("data", ParameterType.LIST, "Array to filter"),
                Parameter("field", ParameterType.STRING, "Field name to check on each item"),
                Parameter("value", ParameterType.STRING, "Value to match (string comparison)"),
                Parameter("operator", ParameterType.STRING, "Comparison: eq, neq, contains, gt, lt. Default: eq", required=False),
            ],
            returns="Filtered array.",
            safety_level=SafetyLevel.LOW,
            examples=[{"data": [{"status": "active"}, {"status": "inactive"}], "field": "status", "value": "active"}],
        ), self._handle_filter_array)

        self.add_capability(ToolCapability(
            name="extract_keys",
            description="Extract specific keys from each object in an array, returning a simplified array.",
            parameters=[
                Parameter("data", ParameterType.LIST, "Array of objects"),
                Parameter("keys", ParameterType.LIST, "List of key names to keep"),
            ],
            returns="Array with only the specified keys per item.",
            safety_level=SafetyLevel.LOW,
            examples=[{"data": [{"id": 1, "name": "Alice", "age": 30}], "keys": ["id", "name"]}],
        ), self._handle_extract_keys)

        self.add_capability(ToolCapability(
            name="diff",
            description="Compare two JSON objects and return added, removed, and changed keys.",
            parameters=[
                Parameter("original", ParameterType.DICT, "Original object"),
                Parameter("updated", ParameterType.DICT, "Updated object"),
            ],
            returns="Dict with added, removed, changed keys.",
            safety_level=SafetyLevel.LOW,
            examples=[{"original": {"a": 1, "b": 2}, "updated": {"b": 99, "c": 3}}],
        ), self._handle_diff)

        self.add_capability(ToolCapability(
            name="validate_schema",
            description="Validate a JSON object against a simple required-fields schema.",
            parameters=[
                Parameter("data", ParameterType.DICT, "Object to validate"),
                Parameter("required_fields", ParameterType.LIST, "List of required field names"),
                Parameter("field_types", ParameterType.DICT, "Optional dict mapping field name to expected type: string, number, boolean, array, object", required=False),
            ],
            returns="Dict with valid (bool), missing_fields, type_errors.",
            safety_level=SafetyLevel.LOW,
            examples=[{"data": {"name": "Alice"}, "required_fields": ["name", "email"]}],
        ), self._handle_validate_schema)

        self.add_capability(ToolCapability(
            name="transform",
            description="Remap keys in each object of an array using a field mapping dict.",
            parameters=[
                Parameter("data", ParameterType.LIST, "Array of objects to transform"),
                Parameter("mapping", ParameterType.DICT, "Dict mapping old_key → new_key"),
            ],
            returns="Transformed array.",
            safety_level=SafetyLevel.LOW,
            examples=[{"data": [{"firstName": "Alice"}], "mapping": {"firstName": "name"}}],
        ), self._handle_transform)

    # ── Handlers ──────────────────────────────────────────────────────────────

    def _handle_parse(self, text: str, **kwargs):
        if not text:
            raise ValueError("text is required")
        return json.loads(text)

    def _handle_stringify(self, data, indent: int = 2, sort_keys: bool = False, **kwargs) -> str:
        if data is None:
            raise ValueError("data is required")
        return json.dumps(data, indent=indent, sort_keys=bool(sort_keys), ensure_ascii=False)

    def _handle_query(self, data, path: str, **kwargs):
        if data is None:
            raise ValueError("data is required")
        result = data
        for key in path.split("."):
            if not key:
                continue
            if isinstance(result, list):
                try:
                    result = result[int(key)]
                except (ValueError, IndexError) as e:
                    raise KeyError(f"Array index '{key}' invalid: {e}")
            elif isinstance(result, dict):
                if key not in result:
                    raise KeyError(f"Key '{key}' not found")
                result = result[key]
            else:
                raise TypeError(f"Cannot traverse into {type(result).__name__} at key '{key}'")
        return result

    def _handle_merge(self, base: dict, override: dict, **kwargs) -> dict:
        def _deep_merge(b, o):
            if isinstance(b, dict) and isinstance(o, dict):
                result = dict(b)
                for k, v in o.items():
                    result[k] = _deep_merge(b.get(k), v)
                return result
            return o if o is not None else b
        return _deep_merge(base or {}, override or {})

    def _handle_flatten(self, data: dict, separator: str = ".", **kwargs) -> dict:
        sep = separator or "."
        def _flatten(obj, prefix=""):
            items = {}
            if isinstance(obj, dict):
                for k, v in obj.items():
                    new_key = f"{prefix}{sep}{k}" if prefix else k
                    items.update(_flatten(v, new_key))
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    new_key = f"{prefix}{sep}{i}" if prefix else str(i)
                    items.update(_flatten(v, new_key))
            else:
                items[prefix] = obj
            return items
        return _flatten(data or {})

    def _handle_filter_array(self, data: list, field: str, value: str, operator: str = "eq", **kwargs) -> list:
        if not isinstance(data, list):
            raise ValueError("data must be an array")
        op = (operator or "eq").lower()
        result = []
        for item in data:
            if not isinstance(item, dict):
                continue
            item_val = item.get(field)
            item_str = str(item_val) if item_val is not None else ""
            if op == "eq" and item_str == str(value):
                result.append(item)
            elif op == "neq" and item_str != str(value):
                result.append(item)
            elif op == "contains" and str(value).lower() in item_str.lower():
                result.append(item)
            elif op == "gt":
                try:
                    if float(item_val) > float(value):
                        result.append(item)
                except (TypeError, ValueError):
                    pass
            elif op == "lt":
                try:
                    if float(item_val) < float(value):
                        result.append(item)
                except (TypeError, ValueError):
                    pass
        return result

    def _handle_extract_keys(self, data: list, keys: list, **kwargs) -> list:
        if not isinstance(data, list):
            raise ValueError("data must be an array")
        return [{k: item.get(k) for k in keys} for item in data if isinstance(item, dict)]

    def _handle_diff(self, original: dict, updated: dict, **kwargs) -> dict:
        orig = original or {}
        upd = updated or {}
        all_keys = set(orig) | set(upd)
        added = {k: upd[k] for k in all_keys if k not in orig}
        removed = {k: orig[k] for k in all_keys if k not in upd}
        changed = {k: {"from": orig[k], "to": upd[k]} for k in all_keys if k in orig and k in upd and orig[k] != upd[k]}
        return {"added": added, "removed": removed, "changed": changed, "unchanged_count": len(all_keys) - len(added) - len(removed) - len(changed)}

    def _handle_validate_schema(self, data: dict, required_fields: list, field_types: dict = None, **kwargs) -> dict:
        if not isinstance(data, dict):
            raise ValueError("data must be an object")
        missing = [f for f in (required_fields or []) if f not in data]
        type_errors = []
        type_map = {"string": str, "number": (int, float), "boolean": bool, "array": list, "object": dict}
        for field, expected_type in (field_types or {}).items():
            if field in data:
                expected = type_map.get(expected_type)
                if expected and not isinstance(data[field], expected):
                    type_errors.append({"field": field, "expected": expected_type, "got": type(data[field]).__name__})
        return {"valid": not missing and not type_errors, "missing_fields": missing, "type_errors": type_errors}

    def _handle_transform(self, data: list, mapping: dict, **kwargs) -> list:
        if not isinstance(data, list):
            raise ValueError("data must be an array")
        result = []
        for item in data:
            if not isinstance(item, dict):
                result.append(item)
                continue
            new_item = {}
            for k, v in item.items():
                new_key = mapping.get(k, k)
                new_item[new_key] = v
            result.append(new_item)
        return result

    def execute(self, operation: str, parameters: dict) -> ToolResult:
        if operation in self._capabilities:
            return self.execute_capability(operation, **parameters)
        return ToolResult(
            tool_name=self.name, capability_name=operation,
            status=ResultStatus.FAILURE, error_message=f"Unknown operation: {operation}",
        )
