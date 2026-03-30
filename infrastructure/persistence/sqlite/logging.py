"""SQLite-based logging system - replaces jsonl files."""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from enum import Enum
from shared.utils.correlation_context import CorrelationContext
from infrastructure.persistence.sqlite.cua_database import get_conn


class LogLevel(Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class SQLiteLogger:
    """SQLite-based structured logger — writes to cua.db."""

    def __init__(self, db_path: str = "data/cua.db", service_name: str = "cua"):
        from infrastructure.persistence.sqlite.cua_database import _ensure_init
        _ensure_init()
        self.service_name = service_name
        self.enabled = True

    def _init_db(self):
        pass  # schema in cua_db
    
    def _log(self, level: LogLevel, message: str, **context):
        """Write log entry to cua.db."""
        timestamp = datetime.now().isoformat()
        correlation_id = CorrelationContext.get_id()
        context_json = json.dumps(context) if context else None
        if self.enabled:
            try:
                with get_conn() as conn:
                    conn.execute(
                        "INSERT INTO logs (timestamp, correlation_id, service, level, message, context) VALUES (?, ?, ?, ?, ?, ?)",
                        (timestamp, correlation_id, self.service_name, level.value, message, context_json)
                    )
            except Exception:
                self.enabled = False
        corr_str = f" [{correlation_id[:8]}]" if correlation_id else ""
        print(f"[{level.value.upper()}]{corr_str} {self.service_name}: {message}")
    
    def debug(self, message: str, **context):
        self._log(LogLevel.DEBUG, message, **context)
    
    def info(self, message: str, **context):
        self._log(LogLevel.INFO, message, **context)
    
    def warning(self, message: str, **context):
        self._log(LogLevel.WARNING, message, **context)
    
    def error(self, message: str, **context):
        self._log(LogLevel.ERROR, message, **context)
    
    def critical(self, message: str, **context):
        self._log(LogLevel.CRITICAL, message, **context)
    
    def log_request(self, session_id: str, user_message: str, **context):
        self.info("user_request", session_id=session_id, user_message=user_message, **context)
    
    def log_plan_generation(self, plan_id: str, steps: int, confidence: float):
        self.info("plan_generated", plan_id=plan_id, steps=steps, confidence=confidence)
    
    def log_execution(self, execution_id: str, status: str, steps_completed: int, steps_total: int):
        self.info("execution_progress", execution_id=execution_id, status=status,
                 steps_completed=steps_completed, steps_total=steps_total)
    
    def log_error(self, error_type: str, error_message: str, **context):
        self.error("error_occurred", error_type=error_type, error_message=error_message, **context)
    
    def query_logs(self, level: Optional[str] = None, service: Optional[str] = None,
                   limit: int = 100, offset: int = 0):
        """Query logs from cua.db."""
        query = "SELECT * FROM logs WHERE 1=1"
        params = []
        if level:
            query += " AND level = ?"
            params.append(level)
        if service:
            query += " AND service = ?"
            params.append(service)
        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with get_conn() as conn:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]


_loggers: Dict[str, SQLiteLogger] = {}


def get_logger(service_name: str = "cua") -> SQLiteLogger:
    """Get or create logger for service."""
    global _loggers
    if service_name not in _loggers:
        _loggers[service_name] = SQLiteLogger(service_name=service_name)
    return _loggers[service_name]
