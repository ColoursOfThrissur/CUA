"""
Improvement Memory System - Tracks past improvement attempts and outcomes.
Writes to cua.db (improvements table) — single source of truth.
"""
from datetime import datetime
from typing import List, Dict, Optional
import json

from infrastructure.persistence.sqlite.cua_database import get_conn


class ImprovementMemory:
    def __init__(self, db_path: str = None):  # db_path kept for API compat, ignored
        pass  # table already created by cua_db._create_all_tables

    def store_attempt(self, file_path: str, change_type: str, description: str,
                      patch: str, outcome: str, error_message: str = None,
                      test_results: dict = None, metrics: dict = None):
        with get_conn() as conn:
            conn.execute("""
                INSERT INTO improvements
                (timestamp, file_path, change_type, description, patch, outcome,
                 error_message, test_results, metrics)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(), file_path, change_type, description,
                patch, outcome, error_message,
                json.dumps(test_results) if test_results else None,
                json.dumps(metrics) if metrics else None,
            ))

    def get_similar_attempts(self, file_path: str, limit: int = 5) -> List[Dict]:
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT timestamp, change_type, description, outcome, error_message
                FROM improvements WHERE file_path = ?
                ORDER BY timestamp DESC LIMIT ?
            """, (file_path, limit)).fetchall()
        return [dict(r) for r in rows]

    def get_failed_attempts(self, days: int = 7) -> List[Dict]:
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT file_path, change_type, description, error_message
                FROM improvements
                WHERE outcome = 'failed'
                AND datetime(timestamp) > datetime('now', '-' || ? || ' days')
                ORDER BY timestamp DESC
            """, (days,)).fetchall()
        return [dict(r) for r in rows]

    def get_successful_attempts(self, days: int = 30) -> List[Dict]:
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT file_path, change_type, description
                FROM improvements
                WHERE outcome = 'success'
                AND datetime(timestamp) > datetime('now', '-' || ? || ' days')
                ORDER BY timestamp DESC
            """, (days,)).fetchall()
        return [dict(r) for r in rows]

    def get_success_rate(self, file_path: str = None) -> float:
        with get_conn() as conn:
            if file_path:
                row = conn.execute("""
                    SELECT SUM(CASE WHEN outcome='success' THEN 1 ELSE 0 END) * 1.0 / COUNT(*)
                    FROM improvements WHERE file_path = ?
                """, (file_path,)).fetchone()
            else:
                row = conn.execute("""
                    SELECT SUM(CASE WHEN outcome='success' THEN 1 ELSE 0 END) * 1.0 / COUNT(*)
                    FROM improvements
                """).fetchone()
        return float(row[0] or 0.0)
