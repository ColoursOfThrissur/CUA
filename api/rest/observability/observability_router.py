"""Observability API - unified access to the consolidated cua.db."""
from fastapi import APIRouter, Query
from typing import Optional
from infrastructure.persistence.sqlite.cua_database import get_conn

router = APIRouter()

# All tables now live in cua.db — map legacy endpoint names to table names
_TABLE_MAP = {
    "logs": "logs",
    "tool_executions": "executions",
    "tool_creation": "tool_creations",
    "tool_evolution": "evolution_runs",
    "chat": "conversations",
}


def query_table(table_name: str, limit: int = 100, offset: int = 0):
    """Query a table from cua.db."""
    try:
        with get_conn() as conn:
            cursor = conn.execute(
                f"SELECT * FROM {table_name} ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset)
            )
            return [dict(row) for row in cursor.fetchall()]
    except Exception:
        return []


@router.get("/observability/logs")
async def get_logs(limit: int = Query(100, le=1000), offset: int = 0):
    return {"data": query_table("logs", limit, offset)}


@router.get("/observability/tool-executions")
async def get_tool_executions(limit: int = Query(100, le=1000), offset: int = 0):
    return {"data": query_table("executions", limit, offset)}


@router.get("/observability/tool-creation")
async def get_tool_creation(limit: int = Query(100, le=1000), offset: int = 0):
    return {"data": query_table("tool_creations", limit, offset)}


@router.get("/observability/tool-evolution")
async def get_tool_evolution(limit: int = Query(100, le=1000), offset: int = 0):
    return {"data": query_table("evolution_runs", limit, offset)}


@router.get("/observability/chat")
async def get_chat_history(limit: int = Query(100, le=1000), offset: int = 0):
    return {"data": query_table("conversations", limit, offset)}
