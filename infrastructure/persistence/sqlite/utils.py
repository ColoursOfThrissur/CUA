"""
SQLite helpers.

Goal: SQLite issues (readonly/locked/corrupt db) must not crash core execution paths.
Callers should treat a None connection as "storage temporarily unavailable".

Note: New code should use core.cua_db.get_conn() instead of safe_connect().
safe_connect() is kept for legacy callers that still open their own DB files.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional, Union

from infrastructure.persistence.sqlite.logging import get_logger

logger = get_logger("sqlite_utils")


DbPath = Union[str, Path]


def safe_connect(db_path: DbPath, *, timeout: float = 5.0) -> Optional[sqlite3.Connection]:
    """
    Best-effort sqlite3.connect with WAL mode enabled.

    Returns:
        sqlite3.Connection or None if the DB cannot be opened.
    """
    path = str(db_path)
    try:
        conn = sqlite3.connect(path, timeout=timeout)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn
    except sqlite3.Error as e:
        logger.warning(f"SQLite unavailable for {path}: {e}")
        return None


def safe_close(conn: Optional[sqlite3.Connection]) -> None:
    """Close sqlite connection, ignoring close-time errors."""
    if not conn:
        return
    try:
        conn.close()
    except Exception:
        return
