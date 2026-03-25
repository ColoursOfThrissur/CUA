"""Observability data API - Query endpoints for the consolidated cua.db"""
from fastapi import APIRouter, Query
from typing import Optional
from core.cua_db import get_conn, DB_PATH

router = APIRouter()

# All tables now live in cua.db — db_name in URL paths is ignored (kept for UI compat)
_ALL_TABLES = [
    {"db": "cua.db", "table": "logs",                    "label": "System Logs"},
    {"db": "cua.db", "table": "executions",              "label": "Tool Executions"},
    {"db": "cua.db", "table": "execution_context",       "label": "Execution Context"},
    {"db": "cua.db", "table": "evolution_runs",          "label": "Tool Evolution"},
    {"db": "cua.db", "table": "evolution_artifacts",     "label": "Evolution Artifacts"},
    {"db": "cua.db", "table": "tool_creations",          "label": "Tool Creation"},
    {"db": "cua.db", "table": "creation_artifacts",      "label": "Creation Artifacts"},
    {"db": "cua.db", "table": "conversations",           "label": "Conversations"},
    {"db": "cua.db", "table": "sessions",                "label": "Sessions"},
    {"db": "cua.db", "table": "learned_patterns",        "label": "Learned Patterns"},
    {"db": "cua.db", "table": "improvement_metrics",     "label": "Improvement Metrics"},
    {"db": "cua.db", "table": "failures",                "label": "Failure Patterns"},
    {"db": "cua.db", "table": "risk_weights",            "label": "Risk Weights"},
    {"db": "cua.db", "table": "improvements",            "label": "Improvements"},
    {"db": "cua.db", "table": "plan_history",            "label": "Plan History"},
    {"db": "cua.db", "table": "tool_metrics_hourly",     "label": "Tool Metrics (Hourly)"},
    {"db": "cua.db", "table": "system_metrics_hourly",   "label": "System Metrics (Hourly)"},
    {"db": "cua.db", "table": "auto_evolution_metrics",  "label": "Auto-Evolution Metrics"},
]


@router.get("/observability/tables")
async def get_tables():
    """Get all available tables with row counts from cua.db."""
    result = []
    for entry in _ALL_TABLES:
        try:
            with get_conn() as conn:
                cur = conn.execute(f"SELECT COUNT(*) FROM {entry['table']}")
                count = cur.fetchone()[0]
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
    """Get paginated table data from cua.db (db_name ignored)."""
    try:
        with get_conn() as conn:
            cur = conn.execute(f"PRAGMA table_info({table_name})")
            columns = [row[1] for row in cur.fetchall()]
            if not columns:
                return {"error": "Table not found", "rows": [], "total": 0}
            order_col = "id" if "id" in columns else "rowid"

            query = f"SELECT * FROM {table_name} WHERE 1=1"
            params = []
            if search:
                conds = [f"{c} LIKE ?" for c in columns]
                query += f" AND ({' OR '.join(conds)})"
                params.extend([f"%{search}%"] * len(columns))
            if filter_column and filter_value:
                query += f" AND {filter_column} = ?"
                params.append(filter_value)

            total = conn.execute(query.replace("SELECT *", "SELECT COUNT(*)"), params).fetchone()[0]
            query += f" ORDER BY {order_col} DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            rows = [dict(r) for r in conn.execute(query, params).fetchall()]
        return {"rows": rows, "total": total, "columns": columns}
    except Exception as e:
        return {"error": str(e), "rows": [], "total": 0}


@router.get("/observability/detail/{db_name}/{table_name}/{row_id}")
async def get_row_detail(db_name: str, table_name: str, row_id: int):
    """Get a single row from cua.db."""
    try:
        with get_conn() as conn:
            row = conn.execute(f"SELECT * FROM {table_name} WHERE rowid = ?", [row_id]).fetchone()
        return {"detail": dict(row)} if row else {"error": "Row not found"}
    except Exception as e:
        return {"error": str(e)}


@router.get("/observability/filters/{db_name}/{table_name}/{column}")
async def get_filter_values(db_name: str, table_name: str, column: str):
    """Get unique values for a column filter dropdown."""
    try:
        with get_conn() as conn:
            rows = conn.execute(
                f"SELECT DISTINCT {column} FROM {table_name} WHERE {column} IS NOT NULL ORDER BY {column} LIMIT 100"
            ).fetchall()
        return {"values": [r[0] for r in rows]}
    except Exception as e:
        return {"error": str(e), "values": []}
