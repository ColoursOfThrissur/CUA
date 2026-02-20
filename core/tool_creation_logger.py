"""Tool creation execution logging."""
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional


class ToolCreationLogger:
    """Log all tool creation attempts."""
    
    def __init__(self, db_path: str = "data/tool_creation.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS creation_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_name TEXT,
                    description TEXT NOT NULL,
                    status TEXT NOT NULL,
                    step TEXT,
                    error_message TEXT,
                    confidence REAL,
                    timestamp TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON creation_runs(status)")
            conn.commit()
    
    def log_run(self, description: str, tool_name: Optional[str], status: str, 
                step: Optional[str] = None, error_message: Optional[str] = None,
                confidence: Optional[float] = None):
        """Log creation run."""
        timestamp = datetime.now().isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO creation_runs 
                   (tool_name, description, status, step, error_message, confidence, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (tool_name, description, status, step, error_message, confidence, timestamp)
            )
            conn.commit()


_logger = None


def get_creation_logger() -> ToolCreationLogger:
    """Get singleton logger."""
    global _logger
    if _logger is None:
        _logger = ToolCreationLogger()
    return _logger
