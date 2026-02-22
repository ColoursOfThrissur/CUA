"""Tool evolution execution logging."""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from core.correlation_context import CorrelationContext


class ToolEvolutionLogger:
    """Log all tool evolution attempts."""
    
    def __init__(self, db_path: str = "data/tool_evolution.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='evolution_runs'")
            table_exists = cursor.fetchone() is not None
            
            if table_exists:
                cursor = conn.execute("PRAGMA table_info(evolution_runs)")
                columns = [row[1] for row in cursor.fetchall()]
                if 'correlation_id' not in columns:
                    conn.execute("ALTER TABLE evolution_runs ADD COLUMN correlation_id TEXT")
                if 'health_after' not in columns:
                    conn.execute("ALTER TABLE evolution_runs ADD COLUMN health_after REAL")
            else:
                conn.execute("""
                    CREATE TABLE evolution_runs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        correlation_id TEXT,
                        tool_name TEXT NOT NULL,
                        user_prompt TEXT,
                        status TEXT NOT NULL,
                        step TEXT,
                        error_message TEXT,
                        confidence REAL,
                        health_before REAL,
                        health_after REAL,
                        timestamp TEXT NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tool_name ON evolution_runs(tool_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON evolution_runs(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_correlation_id ON evolution_runs(correlation_id)")
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS evolution_artifacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    evolution_id INTEGER NOT NULL,
                    correlation_id TEXT,
                    artifact_type TEXT NOT NULL,
                    step TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (evolution_id) REFERENCES evolution_runs(id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_artifacts_evolution_id ON evolution_artifacts(evolution_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_artifacts_type ON evolution_artifacts(artifact_type)")
            conn.commit()
    
    def log_run(self, tool_name: str, user_prompt: Optional[str], status: str, 
                step: Optional[str] = None, error_message: Optional[str] = None,
                confidence: Optional[float] = None, health_before: Optional[float] = None,
                health_after: Optional[float] = None) -> int:
        """Log evolution run. Returns evolution_id."""
        timestamp = datetime.now().isoformat()
        correlation_id = CorrelationContext.get_id()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """INSERT INTO evolution_runs 
                   (correlation_id, tool_name, user_prompt, status, step, error_message, confidence, health_before, health_after, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (correlation_id, tool_name, user_prompt, status, step, error_message, confidence, health_before, health_after, timestamp)
            )
            conn.commit()
            return cursor.lastrowid
    
    def log_artifact(self, evolution_id: int, artifact_type: str, step: str, content: Any):
        """Store evolution artifact (proposal, code, analysis, etc)."""
        timestamp = datetime.now().isoformat()
        correlation_id = CorrelationContext.get_id()
        
        # Convert content to JSON string if dict/list
        if isinstance(content, (dict, list)):
            content_str = json.dumps(content, indent=2)
        else:
            content_str = str(content)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO evolution_artifacts
                   (evolution_id, correlation_id, artifact_type, step, content, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (evolution_id, correlation_id, artifact_type, step, content_str, timestamp)
            )
            conn.commit()
    
    def get_artifacts(self, evolution_id: int) -> list:
        """Get all artifacts for an evolution run."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM evolution_artifacts WHERE evolution_id = ? ORDER BY timestamp",
                (evolution_id,)
            )
            return [dict(row) for row in cursor.fetchall()]


_logger = None


def get_evolution_logger() -> ToolEvolutionLogger:
    """Get singleton logger."""
    global _logger
    if _logger is None:
        _logger = ToolEvolutionLogger()
    return _logger
