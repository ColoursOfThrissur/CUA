"""
Enhanced code validator compatibility layer.

This module now restores the richer contract expected by tool creation,
tool evolution, and service-generation code paths while still returning the
dict-shaped validation payload newer callers use.
"""

from __future__ import annotations

import ast
from typing import Any, Dict, List, Optional

from infrastructure.external.service_registry import SERVICE_METHODS
from infrastructure.validation.ast.security_validator import (
    EnhancedCodeValidator as AstEnhancedCodeValidator,
)


def _build_service_registry() -> Dict[str, List[str]]:
    """Convert service signatures into a method allowlist."""
    registry: Dict[str, List[str]] = {}
    for service_name, signatures in SERVICE_METHODS.items():
        methods: List[str] = []
        for signature in signatures:
            method_name = str(signature).split("(", 1)[0].strip()
            if method_name:
                methods.append(method_name)
        registry[service_name] = methods

    # Direct ToolServices helpers are represented as empty lists.
    registry.update(
        {
            "call_tool": [],
            "list_tools": [],
            "has_capability": [],
            "detect_language": [],
            "extract_key_points": [],
            "sentiment_analysis": [],
            "generate_json_output": [],
        }
    )
    return registry


class EnhancedCodeValidator:
    """Dict-returning validator with backward-compatible service metadata."""

    def __init__(self):
        self.service_registry = _build_service_registry()
        self.available_services = sorted(self.service_registry.keys())
        self._ast_validator = AstEnhancedCodeValidator(
            available_services=self.available_services,
            service_registry=self.service_registry,
        )
        self.dangerous_patterns = [
            "eval",
            "exec",
            "__import__",
            "compile",
            "os.system",
            "subprocess.Popen",
        ]
        self.required_patterns = ["class", "def execute"]

    def validate(self, code: str, context: Optional[Any] = None) -> Dict[str, Any]:
        """Validate code and return the dict payload newer callers expect."""
        class_name = self._resolve_class_name(context)
        errors: List[str] = []
        warnings: List[str] = []

        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            return {
                "valid": False,
                "errors": [f"Syntax error: {exc}"],
                "warnings": [],
                "score": 0,
            }

        # Preserve lightweight warnings the simpler validator already produced.
        for pattern in self.required_patterns:
            if pattern not in code:
                warnings.append(f"Missing recommended pattern: {pattern}")

        classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
        if not classes:
            errors.append("No class definition found")

        if not any(isinstance(node, ast.FunctionDef) and node.name == "execute" for node in ast.walk(tree)):
            warnings.append("No execute method found")

        is_valid, error = self._ast_validator.validate(code, class_name)
        if not is_valid:
            errors.append(error)

        score = 100
        score -= len(errors) * 20
        score -= len(warnings) * 5
        score = max(0, min(100, score))

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "score": score,
        }

    def get_missing_services(self) -> List[Dict[str, str]]:
        """Expose missing services detected by the AST validator."""
        return self._ast_validator.get_missing_services()

    def validate_tool_code(self, code: str, tool_name: str) -> Dict[str, Any]:
        """Validate tool-specific code."""
        return self.validate(code, {"tool_name": tool_name})

    def _resolve_class_name(self, context: Optional[Any]) -> Optional[str]:
        """Accept legacy class-name strings and newer dict contexts."""
        if isinstance(context, str):
            return context or None
        if isinstance(context, dict):
            explicit = context.get("class_name")
            if explicit:
                return str(explicit)
        return None
