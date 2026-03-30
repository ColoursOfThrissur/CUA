"""Metrics API for observability dashboard."""
from fastapi import APIRouter, Query
from typing import Optional
from infrastructure.metrics.aggregator import get_metrics_aggregator
from infrastructure.persistence.sqlite.utils import safe_connect, safe_close

router = APIRouter(prefix="/metrics", tags=["metrics"])

@router.get("/tool/{tool_name}")
async def get_tool_metrics(
    tool_name: str,
    hours: int = Query(24, ge=1, le=168, description="Hours of data to retrieve")
):
    """Get metrics for a specific tool."""
    aggregator = get_metrics_aggregator()
    metrics = aggregator.get_tool_metrics(tool_name, hours)
    
    return {
        "tool_name": tool_name,
        "hours": hours,
        "metrics": metrics,
        "count": len(metrics)
    }

@router.get("/system")
async def get_system_metrics(
    hours: int = Query(24, ge=1, le=168, description="Hours of data to retrieve")
):
    """Get system-wide metrics."""
    aggregator = get_metrics_aggregator()
    metrics = aggregator.get_system_metrics(hours)
    
    return {
        "hours": hours,
        "metrics": metrics,
        "count": len(metrics)
    }

@router.post("/aggregate")
async def trigger_aggregation():
    """Manually trigger metrics aggregation."""
    aggregator = get_metrics_aggregator()
    aggregator.run_aggregation()
    
    return {"status": "success", "message": "Metrics aggregation completed"}

@router.get("/summary")
async def get_metrics_summary():
    """Get summary of latest metrics."""
    aggregator = get_metrics_aggregator()
    
    # Get last hour system metrics
    system_metrics = aggregator.get_system_metrics(hours=1)
    latest_system = system_metrics[0] if system_metrics else None
    
    # Get top tools by execution count
    import sqlite3
    from pathlib import Path
    
    metrics_db = Path("data/metrics.db")
    top_tools = []
    
    if metrics_db.exists():
        conn = safe_connect(metrics_db)
        if conn:
            try:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                SELECT tool_name, SUM(total_executions) as total
                FROM tool_metrics_hourly
                WHERE hour_timestamp >= ?
                GROUP BY tool_name
                ORDER BY total DESC
                LIMIT 10
            """, (int(time.time() // 3600) * 3600 - 86400,))  # Last 24 hours
            
                top_tools = [dict(row) for row in cursor.fetchall()]
            finally:
                safe_close(conn)
    
    return {
        "latest_system_metrics": latest_system,
        "top_tools_24h": top_tools
    }

import time
