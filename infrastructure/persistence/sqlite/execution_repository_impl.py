"""Execution-repository implementation backed by `cua.db`."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from domain.repositories.execution_repository import IExecutionRepository
from infrastructure.logging.tool_execution_logger import get_execution_logger
from infrastructure.persistence.sqlite.cua_database import get_conn


class ExecutionRepository(IExecutionRepository):
    """Provides a small application-facing view over execution persistence."""

    def __init__(self, execution_logger=None):
        self.execution_logger = execution_logger or get_execution_logger()

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
        return self.execution_logger.log_execution(
            tool_name=tool_name,
            operation=operation,
            success=success,
            error=error,
            execution_time_ms=execution_time_ms,
            parameters=parameters or {},
            output_data=output_data,
        )

    def get_recent_executions(self, tool_name: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        query = """
            SELECT id, tool_name, operation, success, error, execution_time_ms, parameters, output_data, created_at
            FROM executions
        """
        params: List[Any] = []
        if tool_name:
            query += " WHERE tool_name = ?"
            params.append(tool_name)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        with get_conn() as conn:
            rows = conn.execute(query, params).fetchall()

        results = []
        for row in rows:
            entry = dict(row)
            for key in ("parameters", "output_data"):
                value = entry.get(key)
                if isinstance(value, str):
                    try:
                        entry[key] = json.loads(value)
                    except Exception:
                        pass
            results.append(entry)
        return results
