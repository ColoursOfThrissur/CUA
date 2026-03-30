"""LLM Test Logger - Store test results in observability system."""
import sqlite3
import json
import time
from pathlib import Path
from typing import Optional, Dict, Any
from shared.utils.correlation_context import CorrelationContext
from infrastructure.persistence.sqlite.logging import get_logger
from infrastructure.persistence.sqlite.utils import safe_connect, safe_close

logger = get_logger("llm_test_logger")

class LLMTestLogger:
    """Logs LLM test executions and results."""
    
    def __init__(self, db_path: str = "data/llm_tests.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema."""
        conn = safe_connect(self.db_path)
        if not conn:
            logger.warning("LLM tests DB unavailable; LLM test logging disabled for now")
            return
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS llm_tests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    correlation_id TEXT,
                    tool_name TEXT NOT NULL,
                    capability_name TEXT NOT NULL,
                    test_name TEXT NOT NULL,
                    passed BOOLEAN NOT NULL,
                    execution_time_ms REAL,
                    quality_score INTEGER,
                    test_case TEXT,
                    output TEXT,
                    error TEXT,
                    validation_result TEXT,
                    timestamp REAL NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_tests_tool ON llm_tests(tool_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_tests_capability ON llm_tests(capability_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_tests_correlation ON llm_tests(correlation_id)")
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS test_suites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    correlation_id TEXT,
                    tool_name TEXT NOT NULL,
                    capability_name TEXT NOT NULL,
                    total_tests INTEGER,
                    passed_tests INTEGER,
                    failed_tests INTEGER,
                    overall_quality_score INTEGER,
                    performance_metrics TEXT,
                    timestamp REAL NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_test_suites_tool ON test_suites(tool_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_test_suites_correlation ON test_suites(correlation_id)")
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS test_baselines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_name TEXT NOT NULL,
                    capability_name TEXT NOT NULL,
                    test_name TEXT NOT NULL,
                    baseline_output TEXT,
                    baseline_performance REAL,
                    baseline_quality_score INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(tool_name, capability_name, test_name)
                )
            """)
            
            conn.commit()
        finally:
            safe_close(conn)
    
    def log_test_result(self, tool_name: str, capability_name: str, test_result: Any):
        """Log a single test result."""
        correlation_id = CorrelationContext.get_id()
        
        conn = safe_connect(self.db_path)
        if not conn:
            return
        try:
            conn.execute("""
                INSERT INTO llm_tests
                (correlation_id, tool_name, capability_name, test_name, passed, execution_time_ms,
                 quality_score, test_case, output, error, validation_result, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                correlation_id,
                tool_name,
                capability_name,
                test_result.test_name,
                test_result.passed,
                test_result.execution_time_ms,
                test_result.quality_score,
                json.dumps({}),  # test_case would be stored here
                json.dumps(test_result.output) if test_result.output else None,
                test_result.error,
                json.dumps(test_result.validation_details),
                time.time()
            ))
            conn.commit()
        finally:
            safe_close(conn)
    
    def log_test_suite(self, suite_result: Any):
        """Log entire test suite results."""
        correlation_id = CorrelationContext.get_id()
        
        conn = safe_connect(self.db_path)
        if not conn:
            return
        try:
            conn.execute("""
                INSERT INTO test_suites
                (correlation_id, tool_name, capability_name, total_tests, passed_tests,
                 failed_tests, overall_quality_score, performance_metrics, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                correlation_id,
                suite_result.tool_name,
                suite_result.capability_name,
                suite_result.total_tests,
                suite_result.passed_tests,
                suite_result.failed_tests,
                suite_result.overall_quality_score,
                json.dumps(suite_result.performance_metrics),
                time.time()
            ))
            conn.commit()
            
            # Log individual test results
            for test_result in suite_result.test_results:
                self.log_test_result(suite_result.tool_name, suite_result.capability_name, test_result)
        finally:
            safe_close(conn)
    
    def update_baseline(self, tool_name: str, capability_name: str, test_name: str,
                       output: Any, performance: float, quality_score: int):
        """Update or create baseline for a test."""
        conn = safe_connect(self.db_path)
        if not conn:
            return
        try:
            conn.execute("""
                INSERT OR REPLACE INTO test_baselines
                (tool_name, capability_name, test_name, baseline_output, baseline_performance,
                 baseline_quality_score, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            """, (
                tool_name,
                capability_name,
                test_name,
                json.dumps(output) if output else None,
                performance,
                quality_score
            ))
            conn.commit()
        finally:
            safe_close(conn)
    
    def get_baseline(self, tool_name: str, capability_name: str, test_name: str) -> Optional[Dict]:
        """Get baseline for a test."""
        conn = safe_connect(self.db_path)
        if not conn:
            return None
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM test_baselines
                WHERE tool_name=? AND capability_name=? AND test_name=?
            """, (tool_name, capability_name, test_name))
            
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            safe_close(conn)

_logger = None

def get_llm_test_logger() -> LLMTestLogger:
    """Get singleton logger."""
    global _logger
    if _logger is None:
        _logger = LLMTestLogger()
    return _logger
