"""Cleanup API for observability data."""
from fastapi import APIRouter
import sqlite3
from pathlib import Path

from infrastructure.persistence.sqlite.utils import safe_connect, safe_close

router = APIRouter()


@router.post("/observability/cleanup")
async def cleanup_stale_data():
    """Remove execution logs for tools that don't exist as files."""
    db_path = Path("data/tool_executions.db")
    
    if not db_path.exists():
        return {"removed": 0, "message": "No database found"}
    
    # Get all tool names from database
    conn = safe_connect(db_path)
    if not conn:
        return {"removed": 0, "message": "Database unavailable (locked/readonly)"}
    try:
        cursor = conn.execute("SELECT DISTINCT tool_name FROM executions")
        tool_names = [row[0] for row in cursor.fetchall()]
    finally:
        safe_close(conn)
    
    # Check which tools don't have files
    removed_count = 0
    removed_tools = []
    
    for tool_name in tool_names:
        candidates = [
            Path(f"tools/{tool_name}.py"),
            Path(f"tools/{tool_name.lower()}.py"),
            Path(f"tools/experimental/{tool_name}.py"),
        ]
        
        if not any(p.exists() for p in candidates):
            # Remove from database
            conn = safe_connect(db_path)
            if conn:
                try:
                    conn.execute("DELETE FROM executions WHERE tool_name = ?", (tool_name,))
                    conn.commit()
                finally:
                    safe_close(conn)
            removed_count += 1
            removed_tools.append(tool_name)
    
    return {
        "removed": removed_count,
        "tools": removed_tools,
        "message": f"Removed {removed_count} stale tool(s)"
    }


@router.post("/observability/refresh")
async def refresh_quality_data():
    """Trigger quality data refresh."""
    from domain.services.tool_quality_analyzer import ToolQualityAnalyzer
    from infrastructure.logging.tool_execution_logger import get_execution_logger
    
    analyzer = ToolQualityAnalyzer(get_execution_logger())
    reports = analyzer.analyze_all_tools(days=7, only_existing=True)
    
    return {
        "total_tools": len(reports),
        "healthy": sum(1 for r in reports if r.recommendation == "HEALTHY"),
        "weak": sum(1 for r in reports if r.recommendation in ["IMPROVE", "QUARANTINE"]),
        "message": f"Analyzed {len(reports)} tools"
    }
