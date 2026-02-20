"""Logs all tool executions for quality analysis."""
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Optional


class ToolExecutionLogger:
    """Logs every tool execution to enable quality tracking."""
    
    def __init__(self, db_path: str = "data/tool_executions.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Create executions table if not exists."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS executions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_name TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    error TEXT,
                    execution_time_ms REAL,
                    parameters TEXT,
                    output_size INTEGER,
                    risk_score REAL,
                    timestamp REAL NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tool_name ON executions(tool_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON executions(timestamp)")
    
    def log_execution(
        self,
        tool_name: str,
        operation: str,
        success: bool,
        error: Optional[str],
        execution_time_ms: float,
        parameters: Dict[str, Any],
        output_data: Any
    ):
        """Log a single tool execution."""
        import json
        
        output_size = len(str(output_data)) if output_data else 0
        params_json = json.dumps(parameters) if parameters else "{}"
        
        # Calculate risk score (0-1, higher = riskier)
        risk_score = self._calculate_risk_score(success, error, execution_time_ms, output_size)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO executions 
                (tool_name, operation, success, error, execution_time_ms, parameters, output_size, risk_score, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (tool_name, operation, int(success), error, execution_time_ms, params_json, output_size, risk_score, time.time()))
    
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
