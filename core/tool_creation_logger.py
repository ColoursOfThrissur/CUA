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
        self.enabled = True
        self._init_db()
    
    def _init_db(self):
        try:
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
        except sqlite3.OperationalError as e:
            self.enabled = False
    
    def log_creation(self, tool_name: str, user_prompt: str, status: str, step: Optional[str] = None, 
                     error_message: Optional[str] = None, code_size: int = 0, capabilities_count: int = 0) -> int:
        """Log tool creation. Returns creation_id."""
        correlation_id = CorrelationContext.get_id()
        
        if not self.enabled:
            return -1

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    INSERT INTO tool_creations 
                    (correlation_id, tool_name, user_prompt, status, step, error_message, code_size, capabilities_count, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (correlation_id, tool_name, user_prompt, status, step, error_message, code_size, capabilities_count, time.time()))
                conn.commit()
                return cursor.lastrowid
        except sqlite3.OperationalError:
            self.enabled = False
            return -1

    def update_creation(
        self,
        creation_id: int,
        tool_name: Optional[str] = None,
        user_prompt: Optional[str] = None,
        status: Optional[str] = None,
        step: Optional[str] = None,
        error_message: Optional[str] = None,
        code_size: Optional[int] = None,
        capabilities_count: Optional[int] = None,
    ) -> None:
        """Update an existing tool creation row in-place.

        Keeps all artifacts attached to a single creation_id so debugging and UI views remain coherent.
        """
        updates = []
        values = []

        if tool_name is not None:
            updates.append("tool_name=?")
            values.append(tool_name)
        if user_prompt is not None:
            updates.append("user_prompt=?")
            values.append(user_prompt)
        if status is not None:
            updates.append("status=?")
            values.append(status)
        if step is not None:
            updates.append("step=?")
            values.append(step)
        if error_message is not None:
            updates.append("error_message=?")
            values.append(error_message)
        if code_size is not None:
            updates.append("code_size=?")
            values.append(code_size)
        if capabilities_count is not None:
            updates.append("capabilities_count=?")
            values.append(capabilities_count)

        # Always bump timestamp so "latest" views track progress.
        updates.append("timestamp=?")
        values.append(time.time())

        if not updates:
            return

        values.append(creation_id)
        sql = f"UPDATE tool_creations SET {', '.join(updates)} WHERE id=?"
        if not self.enabled or creation_id <= 0:
            return

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(sql, tuple(values))
                conn.commit()
        except sqlite3.OperationalError:
            self.enabled = False
            return
    
    def log_artifact(self, creation_id: int, artifact_type: str, step: str, content: Any):
        """Store creation artifact (spec, code, validation, etc)."""
        if not self.enabled or creation_id <= 0:
            return

        correlation_id = CorrelationContext.get_id()
        
        if isinstance(content, (dict, list)):
            content_str = json.dumps(content, indent=2)
        else:
            content_str = str(content)
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO creation_artifacts
                    (creation_id, correlation_id, artifact_type, step, content, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (creation_id, correlation_id, artifact_type, step, content_str, time.time()))
                conn.commit()
        except sqlite3.OperationalError:
            self.enabled = False
            return
    
    def get_last_error(self, creation_id: int, step: str) -> Optional[str]:
        """Get last error message from artifacts for a creation."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT content FROM creation_artifacts
                WHERE creation_id = ? AND step = ? AND artifact_type IN ('operation_failed', 'error')
                ORDER BY id DESC LIMIT 1
            """, (creation_id, step))
            row = cursor.fetchone()
            if row:
                try:
                    data = json.loads(row[0])
                    return data.get('error', str(data))
                except:
                    return row[0]
            return None

_logger = None

def get_tool_creation_logger():
    global _logger
    if _logger is None:
        _logger = ToolCreationLogger()
    return _logger
