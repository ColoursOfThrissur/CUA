"""
SQLite helpers.

Goal: SQLite issues (readonly/locked/corrupt db) must not crash core execution paths.
Callers should treat a None connection as "storage temporarily unavailable".
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional, Union

from core.sqlite_logging import get_logger

logger = get_logger("sqlite_utils")


DbPath = Union[str, Path]


def safe_connect(db_path: DbPath, *, timeout: float = 1.0) -> Optional[sqlite3.Connection]:
    """
    Best-effort sqlite3.connect.

    Returns:
        sqlite3.Connection or None if the DB cannot be opened (readonly/locked/etc).
    """
    path = str(db_path)
    try:
        # Default check_same_thread=True is fine; these DBs are accessed synchronously.
        return sqlite3.connect(path, timeout=timeout)
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
