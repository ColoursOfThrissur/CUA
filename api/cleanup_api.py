"""Cleanup API for observability data."""
from fastapi import APIRouter
import sqlite3
from pathlib import Path

router = APIRouter()


@router.post("/observability/cleanup")
async def cleanup_stale_data():
    """Remove execution logs for tools that don't exist as files."""
    db_path = Path("data/tool_executions.db")
    
    if not db_path.exists():
        return {"removed": 0, "message": "No database found"}
    
    # Get all tool names from database
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute("SELECT DISTINCT tool_name FROM executions")
        tool_names = [row[0] for row in cursor.fetchall()]
    
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
            with sqlite3.connect(db_path) as conn:
                conn.execute("DELETE FROM executions WHERE tool_name = ?", (tool_name,))
                conn.commit()
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
    from core.tool_quality_analyzer import ToolQualityAnalyzer
    
    analyzer = ToolQualityAnalyzer()
    reports = analyzer.analyze_all_tools(days=7, only_existing=True)
    
    return {
        "total_tools": len(reports),
        "healthy": sum(1 for r in reports if r.recommendation == "HEALTHY"),
        "weak": sum(1 for r in reports if r.recommendation in ["IMPROVE", "QUARANTINE"]),
        "message": f"Analyzed {len(reports)} tools"
    }
