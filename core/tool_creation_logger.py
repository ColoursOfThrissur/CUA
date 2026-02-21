"""Logs tool creation attempts."""
import sqlite3
import time
from pathlib import Path
from typing import Optional

class ToolCreationLogger:
    def __init__(self, db_path: str = "data/tool_creation.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tool_creations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_name TEXT NOT NULL,
                    user_prompt TEXT,
                    status TEXT NOT NULL,
                    step TEXT,
                    error_message TEXT,
                    code_size INTEGER,
                    capabilities_count INTEGER,
                    timestamp REAL NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tool_name ON tool_creations(tool_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON tool_creations(status)")
    
    def log_creation(self, tool_name: str, user_prompt: str, status: str, step: Optional[str] = None, 
                     error_message: Optional[str] = None, code_size: int = 0, capabilities_count: int = 0):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO tool_creations 
                (tool_name, user_prompt, status, step, error_message, code_size, capabilities_count, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (tool_name, user_prompt, status, step, error_message, code_size, capabilities_count, time.time()))

_logger = None

def get_tool_creation_logger():
    global _logger
    if _logger is None:
        _logger = ToolCreationLogger()
    return _logger
