"""Domain contract for tool registry access."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Set


class IToolRepository(ABC):
    """Abstraction over tool/capability lookup."""

    @abstractmethod
    def get_capabilities(self, preferred_tools: Optional[Set[str]] = None) -> Dict[str, List[Dict[str, Any]]]:
        """Return tool capabilities grouped by tool name."""

    @abstractmethod
    def get_tool(self, tool_name: str) -> Any:
        """Return a tool instance or metadata object by name."""

    @abstractmethod
    def tool_exists(self, tool_name: str) -> bool:
        """Check whether a tool exists."""
