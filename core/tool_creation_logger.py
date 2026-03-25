"""Logs tool creation attempts."""
import sqlite3
import json
import time
from pathlib import Path
from typing import Optional, Any
from core.correlation_context import CorrelationContext
from core.cua_db import get_conn


class ToolCreationLogger:
    def __init__(self, db_path: str = "data/cua.db"):
        from core.cua_db import _ensure_init
        _ensure_init()
        self.enabled = True

    def _init_db(self):
        pass  # schema in cua_db
    
    def log_creation(self, tool_name: str, user_prompt: str, status: str, step: Optional[str] = None,
                     error_message: Optional[str] = None, code_size: int = 0, capabilities_count: int = 0) -> int:
        if not self.enabled:
            return -1
        correlation_id = CorrelationContext.get_id()
        try:
            with get_conn() as conn:
                cursor = conn.execute("""
                    INSERT INTO tool_creations
                    (correlation_id, tool_name, user_prompt, status, step, error_message, code_size, capabilities_count, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (correlation_id, tool_name, user_prompt, status, step, error_message, code_size, capabilities_count, time.time()))
                return cursor.lastrowid
        except Exception:
            self.enabled = False
            return -1

    def update_creation(self, creation_id: int, tool_name: Optional[str] = None,
                        user_prompt: Optional[str] = None, status: Optional[str] = None,
                        step: Optional[str] = None, error_message: Optional[str] = None,
                        code_size: Optional[int] = None, capabilities_count: Optional[int] = None) -> None:
        if not self.enabled or creation_id <= 0:
            return
        updates, values = [], []
        for col, val in [("tool_name", tool_name), ("user_prompt", user_prompt), ("status", status),
                         ("step", step), ("error_message", error_message), ("code_size", code_size),
                         ("capabilities_count", capabilities_count)]:
            if val is not None:
                updates.append(f"{col}=?")
                values.append(val)
        updates.append("timestamp=?")
        values.append(time.time())
        values.append(creation_id)
        try:
            with get_conn() as conn:
                conn.execute(f"UPDATE tool_creations SET {', '.join(updates)} WHERE id=?", tuple(values))
        except Exception:
            self.enabled = False
    
    def log_artifact(self, creation_id: int, artifact_type: str, step: str, content: Any):
        if not self.enabled or creation_id <= 0:
            return
        correlation_id = CorrelationContext.get_id()
        content_str = json.dumps(content, indent=2) if isinstance(content, (dict, list)) else str(content)
        try:
            with get_conn() as conn:
                conn.execute("""
                    INSERT INTO creation_artifacts
                    (creation_id, correlation_id, artifact_type, step, content, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (creation_id, correlation_id, artifact_type, step, content_str, time.time()))
        except Exception:
            self.enabled = False
    
    def get_last_error(self, creation_id: int, step: str) -> Optional[str]:
        with get_conn() as conn:
            cursor = conn.execute("""
                SELECT content FROM creation_artifacts
                WHERE creation_id = ? AND step = ? AND artifact_type IN ('operation_failed', 'error')
                ORDER BY id DESC LIMIT 1
            """, (creation_id, step))
            row = cursor.fetchone()
            if row:
                try:
                    return json.loads(row['content']).get('error', row['content'])
                except Exception:
                    return row['content']
            return None

_logger = None

def get_tool_creation_logger():
    global _logger
    if _logger is None:
        _logger = ToolCreationLogger()
    return _logger
