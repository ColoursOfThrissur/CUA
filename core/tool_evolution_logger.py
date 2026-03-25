"""Tool evolution execution logging."""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from core.correlation_context import CorrelationContext
from core.cua_db import get_conn


class ToolEvolutionLogger:
    """Log all tool evolution attempts."""

    def __init__(self, db_path: str = "data/cua.db"):
        from core.cua_db import _ensure_init
        _ensure_init()
        self.enabled = True

    def _init_db(self):
        pass  # schema in cua_db
    
    def log_run(self, tool_name: str, user_prompt: Optional[str], status: str,
                step: Optional[str] = None, error_message: Optional[str] = None,
                confidence: Optional[float] = None, health_before: Optional[float] = None,
                health_after: Optional[float] = None) -> int:
        """Log evolution run. Returns evolution_id."""
        if not self.enabled:
            return -1
        timestamp = datetime.now().isoformat()
        correlation_id = CorrelationContext.get_id()
        try:
            with get_conn() as conn:
                cursor = conn.execute(
                    """INSERT INTO evolution_runs
                       (correlation_id, tool_name, user_prompt, status, step, error_message, confidence, health_before, health_after, timestamp)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (correlation_id, tool_name, user_prompt, status, step, error_message, confidence, health_before, health_after, timestamp)
                )
                return cursor.lastrowid
        except Exception:
            self.enabled = False
            return -1
    
    def log_artifact(self, evolution_id: int, artifact_type: str, step: str, content: Any):
        """Store evolution artifact."""
        if not self.enabled or evolution_id <= 0:
            return
        timestamp = datetime.now().isoformat()
        correlation_id = CorrelationContext.get_id()
        content_str = json.dumps(content, indent=2) if isinstance(content, (dict, list)) else str(content)
        try:
            with get_conn() as conn:
                conn.execute(
                    """INSERT INTO evolution_artifacts
                       (evolution_id, correlation_id, artifact_type, step, content, timestamp)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (evolution_id, correlation_id, artifact_type, step, content_str, timestamp)
                )
        except Exception:
            self.enabled = False
    
    def get_artifacts(self, evolution_id: int) -> list:
        """Get all artifacts for an evolution run."""
        with get_conn() as conn:
            cursor = conn.execute(
                "SELECT * FROM evolution_artifacts WHERE evolution_id = ? ORDER BY timestamp",
                (evolution_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def get_evolution_details(self, evolution_id: int) -> Optional[Dict[str, Any]]:
        """Get complete evolution details including all artifacts."""
        with get_conn() as conn:
            cursor = conn.execute("SELECT * FROM evolution_runs WHERE id = ?", (evolution_id,))
            run = cursor.fetchone()
            if not run:
                return None
            run_dict = dict(run)
            cursor = conn.execute(
                "SELECT * FROM evolution_artifacts WHERE evolution_id = ? ORDER BY timestamp",
                (evolution_id,)
            )
            run_dict['artifacts'] = {}
            for artifact in cursor.fetchall():
                a = dict(artifact)
                run_dict['artifacts'].setdefault(a['artifact_type'], []).append(a)
            return run_dict
    
    def get_last_error(self, evolution_id: int, step: str) -> Optional[str]:
        """Get last error message from artifacts for retry."""
        with get_conn() as conn:
            cursor = conn.execute(
                """SELECT content FROM evolution_artifacts
                   WHERE evolution_id = ? AND artifact_type = 'error' AND step = ?
                   ORDER BY timestamp DESC LIMIT 1""",
                (evolution_id, step)
            )
            row = cursor.fetchone()
            if row:
                try:
                    return json.loads(row['content']).get('error', row['content'])
                except Exception:
                    return row['content']
            return None


_logger = None


def get_evolution_logger() -> ToolEvolutionLogger:
    """Get singleton logger."""
    global _logger
    if _logger is None:
        _logger = ToolEvolutionLogger()
    return _logger
