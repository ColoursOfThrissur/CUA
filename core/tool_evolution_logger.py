"""Tool evolution execution logging."""
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional


class ToolEvolutionLogger:
    """Log all tool evolution attempts."""
    
    def __init__(self, db_path: str = "data/tool_evolution.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS evolution_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_name TEXT NOT NULL,
                    user_prompt TEXT,
                    status TEXT NOT NULL,
                    step TEXT,
                    error_message TEXT,
                    confidence REAL,
                    health_before REAL,
                    timestamp TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tool_name ON evolution_runs(tool_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON evolution_runs(status)")
            conn.commit()
    
    def log_run(self, tool_name: str, user_prompt: Optional[str], status: str, 
                step: Optional[str] = None, error_message: Optional[str] = None,
                confidence: Optional[float] = None, health_before: Optional[float] = None):
        """Log evolution run."""
        timestamp = datetime.now().isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO evolution_runs 
                   (tool_name, user_prompt, status, step, error_message, confidence, health_before, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (tool_name, user_prompt, status, step, error_message, confidence, health_before, timestamp)
            )
            conn.commit()


_logger = None


def get_evolution_logger() -> ToolEvolutionLogger:
    """Get singleton logger."""
    global _logger
    if _logger is None:
        _logger = ToolEvolutionLogger()
    return _logger
