"""Observability API - unified access to all monitoring databases."""
from fastapi import APIRouter, Query
from typing import Optional
import sqlite3
from pathlib import Path

router = APIRouter()

DB_PATHS = {
    "logs": "data/logs.db",
    "tool_executions": "data/tool_executions.db",
    "tool_creation": "data/tool_creation.db",
    "tool_evolution": "data/tool_evolution.db",
    "chat": "data/chat_history.db"
}


def query_db(db_name: str, limit: int = 100, offset: int = 0):
    """Query database and return results."""
    db_path = Path(DB_PATHS.get(db_name, "data/logs.db"))
    
    if not db_path.exists():
        return []
    
    with sqlite3.connect(db_path) as conn:
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
