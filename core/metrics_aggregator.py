"""Metrics aggregation system for observability."""
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any
import statistics

from core.sqlite_logging import get_logger
from core.sqlite_utils import safe_connect, safe_close

logger = get_logger("metrics_aggregator")

class MetricsAggregator:
    """Aggregates raw execution data into hourly metrics."""
    
    def __init__(self, 
                 executions_db: str = "data/tool_executions.db",
                 metrics_db: str = "data/metrics.db"):
        self.executions_db = Path(executions_db)
        self.metrics_db = Path(metrics_db)
        self.metrics_db.parent.mkdir(exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Initialize metrics database schema."""
        conn = safe_connect(self.metrics_db)
        if not conn:
            logger.warning("Metrics DB unavailable; metrics disabled for now")
            return
        try:
            # Tool metrics by hour
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tool_metrics_hourly (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_name TEXT NOT NULL,
                    hour_timestamp INTEGER NOT NULL,
                    total_executions INTEGER NOT NULL,
                    successes INTEGER NOT NULL,
                    failures INTEGER NOT NULL,
                    avg_duration_ms REAL,
                    p50_duration_ms REAL,
                    p95_duration_ms REAL,
                    p99_duration_ms REAL,
                    error_rate_percent REAL,
                    avg_output_size INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(tool_name, hour_timestamp)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tool_metrics_tool ON tool_metrics_hourly(tool_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tool_metrics_hour ON tool_metrics_hourly(hour_timestamp)")
            
            # System-wide metrics by hour
            conn.execute("""
                CREATE TABLE IF NOT EXISTS system_metrics_hourly (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hour_timestamp INTEGER NOT NULL UNIQUE,
                    total_chat_requests INTEGER DEFAULT 0,
                    total_tool_calls INTEGER NOT NULL,
                    total_evolutions INTEGER DEFAULT 0,
                    evolution_success_rate REAL DEFAULT 0,
                    avg_response_time_ms REAL,
                    unique_tools_used INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_system_metrics_hour ON system_metrics_hourly(hour_timestamp)")
            
            # Auto-evolution metrics (for upcoming feature)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS auto_evolution_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hour_timestamp INTEGER NOT NULL,
                    tools_analyzed INTEGER DEFAULT 0,
                    evolutions_triggered INTEGER DEFAULT 0,
                    evolutions_pending INTEGER DEFAULT 0,
                    evolutions_approved INTEGER DEFAULT 0,
                    evolutions_rejected INTEGER DEFAULT 0,
                    avg_health_improvement REAL DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(hour_timestamp)
                )
            """)
            
            conn.commit()
        finally:
            safe_close(conn)
    
    def aggregate_tool_metrics(self, hours_back: int = 1):
        """Aggregate tool execution data into hourly metrics."""
        current_hour = int(time.time() // 3600) * 3600
        start_hour = current_hour - (hours_back * 3600)
        
        exec_conn = safe_connect(self.executions_db)
        if not exec_conn:
            return
        try:
            exec_conn.row_factory = sqlite3.Row
            
            # Get all tools with executions in time range
            cursor = exec_conn.execute("""
                SELECT DISTINCT tool_name FROM executions
                WHERE timestamp >= ?
            """, (start_hour,))
            
            tools = [row['tool_name'] for row in cursor.fetchall()]
            
            metrics_conn = safe_connect(self.metrics_db)
            if not metrics_conn:
                return
            try:
                for tool_name in tools:
                    # Get executions for this tool in the hour
                    cursor = exec_conn.execute("""
                        SELECT 
                            success,
                            execution_time_ms,
                            output_size
                        FROM executions
                        WHERE tool_name = ? AND timestamp >= ? AND timestamp < ?
                    """, (tool_name, start_hour, start_hour + 3600))
                    
                    executions = cursor.fetchall()
                    if not executions:
                        continue
                    
                    total = len(executions)
                    successes = sum(1 for e in executions if e['success'])
                    failures = total - successes
                    
                    durations = [e['execution_time_ms'] for e in executions if e['execution_time_ms']]
                    output_sizes = [e['output_size'] for e in executions if e['output_size']]
                    
                    avg_duration = statistics.mean(durations) if durations else 0
                    p50 = statistics.median(durations) if durations else 0
                    p95 = statistics.quantiles(durations, n=20)[18] if len(durations) > 20 else (max(durations) if durations else 0)
                    p99 = statistics.quantiles(durations, n=100)[98] if len(durations) > 100 else (max(durations) if durations else 0)
                    
                    error_rate = (failures / total * 100) if total > 0 else 0
                    avg_output = int(statistics.mean(output_sizes)) if output_sizes else 0
                    
                    # Insert or replace metrics
                    metrics_conn.execute("""
                        INSERT OR REPLACE INTO tool_metrics_hourly
                        (tool_name, hour_timestamp, total_executions, successes, failures,
                         avg_duration_ms, p50_duration_ms, p95_duration_ms, p99_duration_ms,
                         error_rate_percent, avg_output_size)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (tool_name, start_hour, total, successes, failures,
                          avg_duration, p50, p95, p99, error_rate, avg_output))
                
                metrics_conn.commit()
            finally:
                safe_close(metrics_conn)
        finally:
            safe_close(exec_conn)
    
    def aggregate_system_metrics(self, hours_back: int = 1):
        """Aggregate system-wide metrics."""
        current_hour = int(time.time() // 3600) * 3600
        start_hour = current_hour - (hours_back * 3600)
        
        exec_conn = safe_connect(self.executions_db)
        if not exec_conn:
            return
        try:
            # Get system-wide stats
            cursor = exec_conn.execute("""
                SELECT 
                    COUNT(*) as total_calls,
                    COUNT(DISTINCT tool_name) as unique_tools,
                    AVG(execution_time_ms) as avg_time
                FROM executions
                WHERE timestamp >= ? AND timestamp < ?
            """, (start_hour, start_hour + 3600))
            
            row = cursor.fetchone()
            total_calls = row[0] if row else 0
            unique_tools = row[1] if row else 0
            avg_time = row[2] if row else 0
            
            # Get evolution stats if available
            evolution_db = Path("data/tool_evolution.db")
            total_evolutions = 0
            success_rate = 0
            
            if evolution_db.exists():
                evo_conn = safe_connect(evolution_db)
                if evo_conn:
                    try:
                        cursor = evo_conn.execute("""
                            SELECT 
                                COUNT(*) as total,
                                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successes
                            FROM evolution_runs
                            WHERE timestamp >= ? AND timestamp < ?
                        """, (datetime.fromtimestamp(start_hour).isoformat(),
                              datetime.fromtimestamp(start_hour + 3600).isoformat()))
                        
                        row = cursor.fetchone()
                        if row and row[0]:
                            total_evolutions = row[0]
                            success_rate = (row[1] / row[0] * 100) if row[0] > 0 else 0
                    finally:
                        safe_close(evo_conn)
            
            metrics_conn = safe_connect(self.metrics_db)
            if not metrics_conn:
                return
            try:
                metrics_conn.execute("""
                    INSERT OR REPLACE INTO system_metrics_hourly
                    (hour_timestamp, total_tool_calls, total_evolutions, evolution_success_rate,
                     avg_response_time_ms, unique_tools_used)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (start_hour, total_calls, total_evolutions, success_rate, avg_time, unique_tools))
                metrics_conn.commit()
            finally:
                safe_close(metrics_conn)
        finally:
            safe_close(exec_conn)
    
    def get_tool_metrics(self, tool_name: str, hours: int = 24) -> List[Dict[str, Any]]:
        """Get tool metrics for last N hours."""
        cutoff = int(time.time() // 3600) * 3600 - (hours * 3600)
        
        conn = safe_connect(self.metrics_db)
        if not conn:
            return []
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM tool_metrics_hourly
                WHERE tool_name = ? AND hour_timestamp >= ?
                ORDER BY hour_timestamp DESC
            """, (tool_name, cutoff))
            
            return [dict(row) for row in cursor.fetchall()]
        finally:
            safe_close(conn)
    
    def get_system_metrics(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get system metrics for last N hours."""
        cutoff = int(time.time() // 3600) * 3600 - (hours * 3600)
        
        conn = safe_connect(self.metrics_db)
        if not conn:
            return []
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM system_metrics_hourly
                WHERE hour_timestamp >= ?
                ORDER BY hour_timestamp DESC
            """, (cutoff,))
            
            return [dict(row) for row in cursor.fetchall()]
        finally:
            safe_close(conn)
    
    def run_aggregation(self):
        """Run full aggregation for last hour."""
        print("Running metrics aggregation...")
        self.aggregate_tool_metrics(hours_back=1)
        self.aggregate_system_metrics(hours_back=1)
        print("Metrics aggregation complete")

_aggregator = None

def get_metrics_aggregator() -> MetricsAggregator:
    """Get singleton aggregator."""
    global _aggregator
    if _aggregator is None:
        _aggregator = MetricsAggregator()
    return _aggregator
