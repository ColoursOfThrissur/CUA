from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from tools.tool_capability import ParameterType


@dataclass
class ParameterResolutionResult:
    resolved_parameters: Dict[str, Any]
    missing_required: List[str]
    auto_filled: Dict[str, Any]


def resolve_tool_parameters(
    tool,
    operation: str,
    provided: Optional[Dict[str, Any]],
    context: Optional[Dict[str, Any]] = None,
) -> ParameterResolutionResult:
    """Resolve operation parameters from explicit input, context, and defaults."""
    provided_params = dict(provided or {})
    resolved = dict(provided_params)
    auto_filled: Dict[str, Any] = {}
    missing_required: List[str] = []
    context_values = dict(context or {})

    capability = _get_capability(tool, operation)
    if capability is None:
        return ParameterResolutionResult(
            resolved_parameters=resolved,
            missing_required=[],
            auto_filled={},
        )

    provided_lookup = {_normalize_key(k): k for k in resolved.keys() if isinstance(k, str)}
    context_lookup = {_normalize_key(k): k for k in context_values.keys() if isinstance(k, str)}

    for param in capability.parameters or []:
        if not getattr(param, "name", None):
            continue
        name = param.name
        normalized_name = _normalize_key(name)

        # Explicit user value takes precedence.
        if name in resolved:
            resolved[name] = _coerce_by_type(resolved[name], param.type)
            continue
        if normalized_name in provided_lookup:
            source_key = provided_lookup[normalized_name]
            resolved[name] = _coerce_by_type(resolved[source_key], param.type)
            if source_key != name:
                del resolved[source_key]
            continue

        # Then infer from prior context.
        if normalized_name in context_lookup:
            source_key = context_lookup[normalized_name]
            inferred = _coerce_by_type(context_values[source_key], param.type)
            resolved[name] = inferred
            auto_filled[name] = inferred
            continue

        # Then apply declared default for optional fields.
        if not param.required:
            if getattr(param, "default", None) is not None:
                default_value = _coerce_by_type(param.default, param.type)
                resolved[name] = default_value
                auto_filled[name] = default_value
            continue

        missing_required.append(name)

    return ParameterResolutionResult(
        resolved_parameters=resolved,
        missing_required=missing_required,
        auto_filled=auto_filled,
    )


def _get_capability(tool, operation: str):
    try:
        capabilities = tool.get_capabilities()
        return capabilities.get(operation)
    except Exception:
        return None


def _normalize_key(key: str) -> str:
    if not isinstance(key, str):
        return ""
    return "".join(ch for ch in key.lower() if ch.isalnum())


def _coerce_by_type(value: Any, param_type: ParameterType) -> Any:
    if value is None:
        return None
    try:
        if param_type == ParameterType.STRING:
            return str(value)
        if param_type == ParameterType.INTEGER:
            if isinstance(value, bool):
                return int(value)
            return int(value)
        if param_type == ParameterType.BOOLEAN:
            if isinstance(value, str):
                lowered = value.strip().lower()
                if lowered in {"true", "1", "yes", "y", "on"}:
                    return True
                if lowered in {"false", "0", "no", "n", "off"}:
                    return False
            return bool(value)
        if param_type == ParameterType.LIST:
            if isinstance(value, list):
                return value
            return [value]
        if param_type == ParameterType.DICT:
            if isinstance(value, dict):
                return value
            return {"value": value}
        if param_type == ParameterType.FILE_PATH:
            return str(value)
    except Exception:
        return value
    return value
