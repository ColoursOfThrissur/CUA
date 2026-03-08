"""Observability API - unified access to all monitoring databases."""
from fastapi import APIRouter, Query
from typing import Optional
import sqlite3
from pathlib import Path

from core.sqlite_utils import safe_connect, safe_close

router = APIRouter()

DATA_DIR = Path(__file__).parent.parent / "data"

DB_PATHS = {
    "logs": DATA_DIR / "logs.db",
    "tool_executions": DATA_DIR / "tool_executions.db",
    "tool_creation": DATA_DIR / "tool_creation.db",
    "tool_evolution": DATA_DIR / "tool_evolution.db",
    "chat": DATA_DIR / "conversations.db"
}


def query_db(db_name: str, limit: int = 100, offset: int = 0):
    """Query database and return results."""
    db_path = DB_PATHS.get(db_name, DATA_DIR / "logs.db")
    
    if not db_path.exists():
        return []
    
    conn = safe_connect(str(db_path))
    if not conn:
        return []
    try:
        conn.row_factory = sqlite3.Row
        
        # Get table name (assume first table)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        
        if not tables:
            return []
        
        table_name = tables[0][0]
        
        cursor = conn.execute(
            f"SELECT * FROM {table_name} ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset)
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        safe_close(conn)


@router.get("/observability/logs")
async def get_logs(limit: int = Query(100, le=1000), offset: int = 0):
    """Get system logs."""
    return {"data": query_db("logs", limit, offset)}


@router.get("/observability/tool-executions")
async def get_tool_executions(limit: int = Query(100, le=1000), offset: int = 0):
    """Get tool execution logs."""
    return {"data": query_db("tool_executions", limit, offset)}


@router.get("/observability/tool-creation")
async def get_tool_creation(limit: int = Query(100, le=1000), offset: int = 0):
    """Get tool creation logs."""
    return {"data": query_db("tool_creation", limit, offset)}


@router.get("/observability/tool-evolution")
async def get_tool_evolution(limit: int = Query(100, le=1000), offset: int = 0):
    """Get tool evolution logs."""
    return {"data": query_db("tool_evolution", limit, offset)}


@router.get("/observability/chat")
async def get_chat_history(limit: int = Query(100, le=1000), offset: int = 0):
    """Get chat history."""
    return {"data": query_db("chat", limit, offset)}
