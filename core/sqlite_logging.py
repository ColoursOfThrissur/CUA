"""SQLite-based logging system - replaces jsonl files."""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from enum import Enum


class LogLevel(Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class SQLiteLogger:
    """SQLite-based structured logger."""
    
    def __init__(self, db_path: str = "data/logs.db", service_name: str = "cua"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(exist_ok=True)
        self.service_name = service_name
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    service TEXT NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    context TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON logs(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_service ON logs(service)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_level ON logs(level)")
            conn.commit()
    
    def _log(self, level: LogLevel, message: str, **context):
        """Write log entry to database."""
        timestamp = datetime.now().isoformat()
        context_json = json.dumps(context) if context else None
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO logs (timestamp, service, level, message, context) VALUES (?, ?, ?, ?, ?)",
                (timestamp, self.service_name, level.value, message, context_json)
            )
            conn.commit()
        
        # Also print to console for immediate feedback
        print(f"[{level.value.upper()}] {self.service_name}: {message}")
    
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
        """Query logs from database."""
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
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]


_loggers: Dict[str, SQLiteLogger] = {}


def get_logger(service_name: str = "cua") -> SQLiteLogger:
    """Get or create logger for service."""
    global _loggers
    if service_name not in _loggers:
        _loggers[service_name] = SQLiteLogger(service_name=service_name)
    return _loggers[service_name]
