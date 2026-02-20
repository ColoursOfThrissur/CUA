"""API endpoints for tool quality analytics."""
from fastapi import APIRouter, HTTPException
from typing import Dict, List, Optional

from core.tool_quality_analyzer import ToolQualityAnalyzer

router = APIRouter()
analyzer = ToolQualityAnalyzer()


@router.get("/quality/summary")
async def get_quality_summary(days: int = 7) -> Dict:
    """Get overall tool ecosystem health summary."""
    try:
        return analyzer.get_summary(days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quality/tool/{tool_name}")
async def get_tool_quality(tool_name: str, days: int = 7) -> Dict:
    """Get quality report for a specific tool."""
    try:
        report = analyzer.analyze_tool(tool_name, days)
        return {
            "tool_name": report.tool_name,
            "success_rate": report.success_rate,
            "usage_frequency": report.usage_frequency,
            "avg_execution_time_ms": report.avg_execution_time_ms,
            "output_richness": report.output_richness,
            "avg_risk_score": report.avg_risk_score,
            "health_score": report.health_score,
            "issues": report.issues,
            "recommendation": report.recommendation
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quality/all")
async def get_all_tools_quality(days: int = 7) -> List[Dict]:
    """Get quality reports for all tools."""
    try:
        reports = analyzer.analyze_all_tools(days)
        return [
            {
                "tool_name": r.tool_name,
                "success_rate": r.success_rate,
                "usage_frequency": r.usage_frequency,
                "avg_execution_time_ms": r.avg_execution_time_ms,
                "output_richness": r.output_richness,
                "avg_risk_score": r.avg_risk_score,
                "health_score": r.health_score,
                "issues": r.issues,
                "recommendation": r.recommendation
            }
            for r in reports
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quality/weak")
async def get_weak_tools(days: int = 7, min_usage: int = 5) -> List[Dict]:
    """Get tools that need improvement."""
    try:
        reports = analyzer.get_weak_tools(days, min_usage)
        return [
            {
                "tool_name": r.tool_name,
                "success_rate": r.success_rate,
                "usage_frequency": r.usage_frequency,
                "avg_risk_score": r.avg_risk_score,
                "health_score": r.health_score,
                "issues": r.issues,
                "recommendation": r.recommendation
            }
            for r in reports
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
