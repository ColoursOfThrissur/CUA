"""Observability data API - Query endpoints for all databases"""
from fastapi import APIRouter, Query
from typing import Optional, List
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

from core.sqlite_utils import safe_connect, safe_close

router = APIRouter()
DATA_DIR = Path(__file__).parent.parent / "data"

@router.get("/observability/tables")
async def get_tables():
    """Get all available tables across databases, dynamically verified against disk."""
    candidates = [
        {"db": "logs.db",              "table": "logs",                    "label": "System Logs"},
        {"db": "tool_executions.db",   "table": "executions",              "label": "Tool Executions"},
        {"db": "tool_executions.db",   "table": "execution_context",       "label": "Execution Context"},
        {"db": "tool_evolution.db",    "table": "evolution_runs",          "label": "Tool Evolution"},
        {"db": "tool_evolution.db",    "table": "evolution_artifacts",     "label": "Evolution Artifacts"},
        {"db": "tool_creation.db",     "table": "tool_creations",          "label": "Tool Creation"},
        {"db": "tool_creation.db",     "table": "creation_artifacts",      "label": "Creation Artifacts"},
        {"db": "conversations.db",     "table": "conversations",           "label": "Conversations"},
        {"db": "conversations.db",     "table": "sessions",                "label": "Sessions"},
        {"db": "conversations.db",     "table": "execution_history",       "label": "Execution History"},
        {"db": "conversations.db",     "table": "learned_patterns",        "label": "Learned Patterns"},
        {"db": "analytics.db",         "table": "improvement_metrics",     "label": "Improvement Metrics"},
        {"db": "analytics.db",         "table": "attempt_terminal_states", "label": "Terminal States"},
        {"db": "failure_patterns.db",  "table": "failures",                "label": "Failure Patterns"},
        {"db": "failure_patterns.db",  "table": "risk_weights",            "label": "Risk Weights"},
        {"db": "improvement_memory.db","table": "improvements",            "label": "Improvements"},
        {"db": "plan_history.db",      "table": "plan_history",            "label": "Plan History"},
        {"db": "metrics.db",           "table": "tool_metrics_hourly",     "label": "Tool Metrics (Hourly)"},
        {"db": "metrics.db",           "table": "system_metrics_hourly",   "label": "System Metrics (Hourly)"},
        {"db": "metrics.db",           "table": "auto_evolution_metrics",  "label": "Auto-Evolution Metrics"},
    ]
    # Annotate with row counts and verify existence
    import sqlite3
    result = []
    for entry in candidates:
        db_path = DATA_DIR / entry["db"]
        if not db_path.exists():
            continue
        try:
            con = sqlite3.connect(str(db_path))
            cur = con.cursor()
            cur.execute(f"SELECT COUNT(*) FROM {entry['table']}")
            count = cur.fetchone()[0]
            con.close()
            result.append({**entry, "row_count": count})
        except Exception:
            pass
    return {"tables": result}

@router.get("/observability/data/{db_name}/{table_name}")
async def get_table_data(
    db_name: str,
    table_name: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    search: Optional[str] = None,
    filter_column: Optional[str] = None,
    filter_value: Optional[str] = None
):
    """Get paginated table data with search and filters"""
    db_path = DATA_DIR / db_name
    if not db_path.exists():
        return {"error": "Database not found", "rows": [], "total": 0}
    
    try:
        conn = safe_connect(str(db_path))
        if not conn:
            return {"error": "Database unavailable (locked/readonly)", "rows": [], "total": 0}
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get columns
        cursor.execute(f"PRAGMA table_info({table_name})")
        col_info = cursor.fetchall()
        columns = [row[1] for row in col_info]
        has_id = "id" in columns
        order_col = "id" if has_id else "rowid"

        # Build query
        query = f"SELECT * FROM {table_name} WHERE 1=1"
        params = []
        
        # Search across all text columns
        if search:
            search_conditions = []
            for col in columns:
                search_conditions.append(f"{col} LIKE ?")
                params.append(f"%{search}%")
            query += f" AND ({' OR '.join(search_conditions)})"
        
        # Filter by specific column
        if filter_column and filter_value:
            query += f" AND {filter_column} = ?"
            params.append(filter_value)
        
        # Get total count
        count_query = query.replace("SELECT *", "SELECT COUNT(*)")
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]
        
        # Get paginated data
        query += f" ORDER BY {order_col} DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        rows = [dict(row) for row in cursor.fetchall()]
        safe_close(conn)
        
        return {"rows": rows, "total": total, "columns": columns}
    except Exception as e:
        return {"error": str(e), "rows": [], "total": 0}

@router.get("/observability/detail/{db_name}/{table_name}/{row_id}")
async def get_row_detail(db_name: str, table_name: str, row_id: int):
    """Get detailed view of a single row"""
    db_path = DATA_DIR / db_name
    if not db_path.exists():
        return {"error": "Database not found"}
    
    try:
        conn = safe_connect(str(db_path))
        if not conn:
            return {"error": "Database unavailable (locked/readonly)"}
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute(f"SELECT * FROM {table_name} WHERE rowid = ?", [row_id])
        row = cursor.fetchone()
        safe_close(conn)
        
        if not row:
            return {"error": "Row not found"}
        
        return {"detail": dict(row)}
    except Exception as e:
        return {"error": str(e)}

@router.get("/observability/filters/{db_name}/{table_name}/{column}")
async def get_filter_values(db_name: str, table_name: str, column: str):
    """Get unique values for a column (for filter dropdowns)"""
    db_path = DATA_DIR / db_name
    if not db_path.exists():
        return {"values": []}
    
    try:
        conn = safe_connect(str(db_path))
        if not conn:
            return {"error": "Database unavailable (locked/readonly)", "values": []}
        cursor = conn.cursor()
        
        cursor.execute(f"SELECT DISTINCT {column} FROM {table_name} WHERE {column} IS NOT NULL ORDER BY {column}")
        values = [row[0] for row in cursor.fetchall()]
        safe_close(conn)
        
        return {"values": values[:100]}  # Limit to 100 unique values
    except Exception as e:
        return {"error": str(e), "values": []}
