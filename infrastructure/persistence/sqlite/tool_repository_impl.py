"""Compatibility tool-repository implementation backed by the live registry."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from application.use_cases.tool_lifecycle.tool_registry_manager import ToolRegistryManager
from domain.repositories.tool_repository import IToolRepository


class ToolRepository(IToolRepository):
    """Reads tool metadata from the centralized tool registry."""

    def __init__(self, registry_manager: Optional[ToolRegistryManager] = None):
        self.registry_manager = registry_manager or ToolRegistryManager()

    def get_capabilities(self, preferred_tools: Optional[Set[str]] = None) -> Dict[str, List[Dict[str, Any]]]:
        registry = self.registry_manager.get_registry() or {}
        tools = registry.get("tools") or {}
        allowed = set(preferred_tools or [])
        result: Dict[str, List[Dict[str, Any]]] = {}

        for tool_name, meta in tools.items():
            if allowed and tool_name not in allowed:
                continue
            operations = meta.get("operations") or {}
            result[tool_name] = [
                {
                    "name": op_name,
                    "description": op_data.get("description", ""),
                    "parameters": [
                        {
                            "name": param_name,
                            "required": param_name in set(op_data.get("required") or []),
                        }
                        for param_name in op_data.get("parameters") or []
                    ],
                }
                for op_name, op_data in operations.items()
            ]

        return result

    def get_tool(self, tool_name: str) -> Any:
        return self.registry_manager.get_tool_info(tool_name)

    def tool_exists(self, tool_name: str) -> bool:
        return self.get_tool(tool_name) is not None
