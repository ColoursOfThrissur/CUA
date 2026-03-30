"""Domain contract for execution history access."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class IExecutionRepository(ABC):
    """Abstraction over execution persistence and lookup."""

    @abstractmethod
    def record_execution(
        self,
        tool_name: str,
        operation: str,
        success: bool,
        error: Optional[str] = None,
        execution_time_ms: float = 0.0,
        parameters: Optional[Dict[str, Any]] = None,
        output_data: Any = None,
    ) -> int:
        """Persist a tool execution and return its identifier."""

    @abstractmethod
    def get_recent_executions(self, tool_name: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """Return recent execution rows, optionally filtered by tool."""
