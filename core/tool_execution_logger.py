"""Logs all tool executions for quality analysis."""
import sqlite3
import time
import json
import traceback
from pathlib import Path
from typing import Any, Dict, Optional
from core.correlation_context import CorrelationContext


class ToolExecutionLogger:
    """Logs every tool execution to enable quality tracking."""
    
    def __init__(self, db_path: str = "data/tool_executions.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Create executions table if not exists."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='executions'")
            table_exists = cursor.fetchone() is not None
            
            if table_exists:
                cursor = conn.execute("PRAGMA table_info(executions)")
                columns = [row[1] for row in cursor.fetchall()]
                if 'correlation_id' not in columns:
                    conn.execute("ALTER TABLE executions ADD COLUMN correlation_id TEXT")
                if 'parent_execution_id' not in columns:
                    conn.execute("ALTER TABLE executions ADD COLUMN parent_execution_id INTEGER")
                if 'error_stack_trace' not in columns:
                    conn.execute("ALTER TABLE executions ADD COLUMN error_stack_trace TEXT")
                if 'output_data' not in columns:
                    conn.execute("ALTER TABLE executions ADD COLUMN output_data TEXT")
            else:
                conn.execute("""
                    CREATE TABLE executions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        correlation_id TEXT,
                        parent_execution_id INTEGER,
                        tool_name TEXT NOT NULL,
                        operation TEXT NOT NULL,
                        success INTEGER NOT NULL,
                        error TEXT,
                        error_stack_trace TEXT,
                        execution_time_ms REAL,
                        parameters TEXT,
                        output_data TEXT,
                        output_size INTEGER,
                        risk_score REAL,
                        timestamp REAL NOT NULL,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tool_name ON executions(tool_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON executions(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_correlation_id ON executions(correlation_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_parent_execution_id ON executions(parent_execution_id)")
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS execution_context (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    execution_id INTEGER NOT NULL,
                    correlation_id TEXT,
                    service_calls TEXT,
                    llm_calls_count INTEGER DEFAULT 0,
                    llm_tokens_used INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (execution_id) REFERENCES executions(id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_exec_context_execution_id ON execution_context(execution_id)")
            conn.commit()
    
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
        if output_data:
            output_str = json.dumps(output_data) if not isinstance(output_data, str) else output_data
            output_json = output_str[:10000] if len(output_str) > 10000 else output_str
        
        # Capture stack trace if error
        error_stack_trace = None
        if error and not success:
            error_stack_trace = traceback.format_exc()
        
        # Calculate risk score (0-1, higher = riskier)
        risk_score = self._calculate_risk_score(success, error, execution_time_ms, output_size)
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    INSERT INTO executions 
                    (correlation_id, parent_execution_id, tool_name, operation, success, error, error_stack_trace, 
                     execution_time_ms, parameters, output_data, output_size, risk_score, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (correlation_id, parent_execution_id, tool_name, operation, int(success), error, 
                      error_stack_trace, execution_time_ms, params_json, output_json, output_size, risk_score, time.time()))
                
                execution_id = cursor.lastrowid
                
                # Store execution context if provided
                if service_calls or llm_calls_count > 0:
                    service_calls_json = json.dumps(service_calls) if service_calls else None
                    conn.execute("""
                        INSERT INTO execution_context
                        (execution_id, correlation_id, service_calls, llm_calls_count, llm_tokens_used)
                        VALUES (?, ?, ?, ?, ?)
                    """, (execution_id, correlation_id, service_calls_json, llm_calls_count, llm_tokens_used))
                
                conn.commit()
                return execution_id
        except sqlite3.OperationalError as e:
            # In some environments (Windows + running server), sqlite files can be locked/readonly.
            # Logging must never break tool execution.
            if "readonly" in str(e).lower() or "read-only" in str(e).lower():
                return -1
            raise
    
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
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT 
                    COUNT(*) as total_executions,
                    SUM(success) as successful_executions,
                    AVG(execution_time_ms) as avg_time_ms,
                    AVG(output_size) as avg_output_size,
                    AVG(risk_score) as avg_risk_score
                FROM executions
                WHERE tool_name = ? AND timestamp > ?
            """, (tool_name, cutoff))
            
            row = cursor.fetchone()
            if not row or row[0] == 0:
                return {
                    "total_executions": 0,
                    "success_rate": 0.0,
                    "avg_time_ms": 0.0,
                    "avg_output_size": 0,
                    "avg_risk_score": 0.0
                }
            
            total, successful, avg_time, avg_size, avg_risk = row
            return {
                "total_executions": total,
                "success_rate": successful / total if total > 0 else 0.0,
                "avg_time_ms": avg_time or 0.0,
                "avg_output_size": int(avg_size or 0),
                "avg_risk_score": avg_risk or 0.0
            }
    
    def get_all_tools_stats(self, days: int = 7) -> Dict[str, Dict[str, Any]]:
        """Get stats for all tools."""
        cutoff = time.time() - (days * 86400)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT 
                    tool_name,
                    COUNT(*) as total,
                    SUM(success) as successful,
                    AVG(execution_time_ms) as avg_time,
                    AVG(output_size) as avg_size,
                    AVG(risk_score) as avg_risk
                FROM executions
                WHERE timestamp > ?
                GROUP BY tool_name
            """, (cutoff,))
            
            results = {}
            for row in cursor.fetchall():
                tool_name, total, successful, avg_time, avg_size, avg_risk = row
                results[tool_name] = {
                    "total_executions": total,
                    "success_rate": successful / total if total > 0 else 0.0,
                    "avg_time_ms": avg_time or 0.0,
                    "avg_output_size": int(avg_size or 0),
                    "avg_risk_score": avg_risk or 0.0
                }
            
            return results


_logger_instance = None

def get_execution_logger() -> ToolExecutionLogger:
    """Get singleton logger instance."""
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = ToolExecutionLogger()
    return _logger_instance
