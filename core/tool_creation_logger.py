"""Logs tool creation attempts."""
import sqlite3
import json
import time
from pathlib import Path
from typing import Optional, Any
from core.correlation_context import CorrelationContext

class ToolCreationLogger:
    def __init__(self, db_path: str = "data/tool_creation.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tool_creations'")
            table_exists = cursor.fetchone() is not None
            
            if table_exists:
                cursor = conn.execute("PRAGMA table_info(tool_creations)")
                columns = [row[1] for row in cursor.fetchall()]
                if 'correlation_id' not in columns:
                    conn.execute("ALTER TABLE tool_creations ADD COLUMN correlation_id TEXT")
            else:
                conn.execute("""
                    CREATE TABLE tool_creations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        correlation_id TEXT,
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
            conn.execute("CREATE INDEX IF NOT EXISTS idx_correlation_id ON tool_creations(correlation_id)")
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS creation_artifacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    creation_id INTEGER NOT NULL,
                    correlation_id TEXT,
                    artifact_type TEXT NOT NULL,
                    step TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (creation_id) REFERENCES tool_creations(id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_creation_artifacts_creation_id ON creation_artifacts(creation_id)")
            conn.commit()
    
    def log_creation(self, tool_name: str, user_prompt: str, status: str, step: Optional[str] = None, 
                     error_message: Optional[str] = None, code_size: int = 0, capabilities_count: int = 0) -> int:
        """Log tool creation. Returns creation_id."""
        correlation_id = CorrelationContext.get_id()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                INSERT INTO tool_creations 
                (correlation_id, tool_name, user_prompt, status, step, error_message, code_size, capabilities_count, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (correlation_id, tool_name, user_prompt, status, step, error_message, code_size, capabilities_count, time.time()))
            conn.commit()
            return cursor.lastrowid
    
    def log_artifact(self, creation_id: int, artifact_type: str, step: str, content: Any):
        """Store creation artifact (spec, code, validation, etc)."""
        correlation_id = CorrelationContext.get_id()
        
        if isinstance(content, (dict, list)):
            content_str = json.dumps(content, indent=2)
        else:
            content_str = str(content)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO creation_artifacts
                (creation_id, correlation_id, artifact_type, step, content, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (creation_id, correlation_id, artifact_type, step, content_str, time.time()))
            conn.commit()

_logger = None

def get_tool_creation_logger():
    global _logger
    if _logger is None:
        _logger = ToolCreationLogger()
    return _logger
