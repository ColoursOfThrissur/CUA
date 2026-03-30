"""Logs all tool executions for quality analysis."""
import sqlite3
import time
import json
import traceback
from pathlib import Path
from typing import Any, Dict, Optional
from shared.utils.correlation_context import CorrelationContext
from infrastructure.persistence.sqlite.cua_database import get_conn


class ToolExecutionLogger:
    """Logs every tool execution to enable quality tracking."""

    def __init__(self, db_path: str = "data/cua.db"):
        # db_path kept for API compat but ignored — all writes go to cua.db via get_conn()
        from infrastructure.persistence.sqlite.cua_database import _ensure_init
        _ensure_init()

    def _init_db(self):
        """No-op — schema created by cua_db._ensure_init."""
        pass

    # legacy _init_db removed — schema lives in cua_db._create_all_tables
    
    def log_execution(
        self,
        tool_name: str,
        operation: str,
        success: bool,
        error: Optional[str],
        execution_time_ms: float,
        parameters: Dict[str, Any],
        output_data: Any,
        parent_execution_id: Optional[int] = None,
        service_calls: Optional[list] = None,
        llm_calls_count: int = 0,
        llm_tokens_used: int = 0
    ) -> int:
        """Log a single tool execution with full context. Returns execution_id."""
        
        correlation_id = CorrelationContext.get_id()
        output_size = len(str(output_data)) if output_data else 0
        params_json = json.dumps(parameters) if parameters else "{}"
        
        # Store full output data (truncate if too large)
        output_json = None
        if output_data is not None:
            output_str = json.dumps(output_data) if not isinstance(output_data, str) else output_data
            output_json = output_str[:10000] if len(output_str) > 10000 else output_str
        
        # Capture stack trace if error
        error_stack_trace = None
        if error and not success:
            error_stack_trace = traceback.format_exc()
        
        # Calculate risk score (0-1, higher = riskier)
        risk_score = self._calculate_risk_score(success, error, execution_time_ms, output_size)
        
        try:
            with get_conn() as conn:
                cursor = conn.execute("""
                    INSERT INTO executions
                    (correlation_id, parent_execution_id, tool_name, operation, success, error, error_stack_trace,
                     execution_time_ms, parameters, output_data, output_size, risk_score, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (correlation_id, parent_execution_id, tool_name, operation, int(success), error,
                      error_stack_trace, execution_time_ms, params_json, output_json, output_size, risk_score, time.time()))
                execution_id = cursor.lastrowid
                if service_calls or llm_calls_count > 0:
                    service_calls_json = json.dumps(service_calls) if service_calls else None
                    conn.execute("""
                        INSERT INTO execution_context
                        (execution_id, correlation_id, service_calls, llm_calls_count, llm_tokens_used)
                        VALUES (?, ?, ?, ?, ?)
                    """, (execution_id, correlation_id, service_calls_json, llm_calls_count, llm_tokens_used))
                return execution_id
        except Exception:
            return -1
    
    def _calculate_risk_score(self, success: bool, error: Optional[str], exec_time_ms: float, output_size: int) -> float:
        """Calculate risk score for execution (0-1, higher = riskier)."""
        risk = 0.0
        
        # Failure adds high risk
        if not success:
            risk += 0.5
            
            # Critical errors add more risk
            if error:
                error_lower = error.lower()
                if any(kw in error_lower for kw in ['timeout', 'memory', 'crash', 'fatal']):
                    risk += 0.3
                elif any(kw in error_lower for kw in ['permission', 'access', 'denied']):
                    risk += 0.2
        
        # Slow execution adds risk
        if exec_time_ms > 5000:
            risk += 0.2
        elif exec_time_ms > 2000:
            risk += 0.1
        
        # No output adds risk
        if output_size == 0:
            risk += 0.1
        
        return min(risk, 1.0)
    
    def get_tool_stats(self, tool_name: str, days: int = 7) -> Dict[str, Any]:
        """Get execution stats for a tool."""
        cutoff = time.time() - (days * 86400)
        
        with get_conn() as conn:
            cursor = conn.execute("""
                SELECT COUNT(*), SUM(success), AVG(execution_time_ms), AVG(output_size), AVG(risk_score)
                FROM executions WHERE tool_name = ? AND timestamp > ?
            """, (tool_name, cutoff))
            row = cursor.fetchone()
            if not row or row[0] == 0:
                return {"total_executions": 0, "success_rate": 0.0, "avg_time_ms": 0.0, "avg_output_size": 0, "avg_risk_score": 0.0}
            total, successful, avg_time, avg_size, avg_risk = row
            return {
                "total_executions": total,
                "success_rate": successful / total if total > 0 else 0.0,
                "avg_time_ms": avg_time or 0.0,
                "avg_output_size": int(avg_size or 0),
                "avg_risk_score": avg_risk or 0.0,
            }
    
    def get_all_tools_stats(self, days: int = 7) -> Dict[str, Dict[str, Any]]:
        """Get stats for all tools."""
        cutoff = time.time() - (days * 86400)
        
        with get_conn() as conn:
            cursor = conn.execute("""
                SELECT tool_name, COUNT(*), SUM(success), AVG(execution_time_ms), AVG(output_size), AVG(risk_score)
                FROM executions WHERE timestamp > ? GROUP BY tool_name
            """, (cutoff,))
            results = {}
            for row in cursor.fetchall():
                tool_name, total, successful, avg_time, avg_size, avg_risk = row
                results[tool_name] = {
                    "total_executions": total,
                    "success_rate": successful / total if total > 0 else 0.0,
                    "avg_time_ms": avg_time or 0.0,
                    "avg_output_size": int(avg_size or 0),
                    "avg_risk_score": avg_risk or 0.0,
                }
            return results


_logger_instance = None

def get_execution_logger() -> ToolExecutionLogger:
    """Get singleton logger instance."""
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = ToolExecutionLogger()
    return _logger_instance
