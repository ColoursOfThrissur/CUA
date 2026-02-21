"""API endpoints for tool quality analytics."""
from fastapi import APIRouter, HTTPException
from typing import Dict, List, Optional

from core.tool_quality_analyzer import ToolQualityAnalyzer
from core.llm_tool_health_analyzer import LLMToolHealthAnalyzer

router = APIRouter()
analyzer = ToolQualityAnalyzer()
llm_analyzer = LLMToolHealthAnalyzer()


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
async def get_weak_tools(days: int = 7, min_usage: int = 5, exclude_pending: bool = True) -> List[Dict]:
    """Get tools that need improvement."""
    try:
        reports = analyzer.get_weak_tools(days, min_usage, exclude_pending)
        return [
            {
                "tool_name": r.tool_name,
                "success_rate": r.success_rate,
                "usage_frequency": r.usage_frequency,
                "avg_risk_score": r.avg_risk_score,
                "health_score": r.health_score,
                "issues": r.issues,
                "recommendation": r.recommendation,
                "has_recent_errors": r.has_recent_errors
            }
            for r in reports
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quality/llm-analysis/{tool_name}")
async def get_llm_analysis(tool_name: str, force_refresh: bool = False) -> Dict:
    """Get LLM-based code analysis for a specific tool."""
    try:
        return llm_analyzer.analyze_tool(tool_name, force_refresh)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quality/llm-analysis-all")
async def get_all_llm_analysis(force_refresh: bool = False) -> Dict:
    """Get LLM-based analysis for all tools."""
    try:
        return llm_analyzer.analyze_all_tools(force_refresh)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quality/llm-weak")
async def get_llm_weak_tools(force_refresh: bool = False, exclude_pending: bool = True) -> List[Dict]:
    """Get tools categorized as WEAK by LLM analysis."""
    try:
        weak_tools = llm_analyzer.get_weak_tools(force_refresh)
        
        if exclude_pending:
            from core.pending_evolutions_manager import PendingEvolutionsManager
            pending_mgr = PendingEvolutionsManager()
            pending = {p["tool_name"] for p in pending_mgr.get_all_pending()}
            weak_tools = [t for t in weak_tools if t["tool_name"] not in pending]
        
        # Add execution error info
        for tool in weak_tools:
            reports = analyzer.analyze_tool(tool["tool_name"], days=7)
            tool["has_recent_errors"] = reports.success_rate < 0.7
            tool["health_score"] = reports.health_score
        
        # Sort: errors first, then by health score
        weak_tools.sort(key=lambda t: (not t.get("has_recent_errors", False), t.get("health_score", 100)))
        
        return weak_tools
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quality/llm-summary")
async def get_llm_summary(force_refresh: bool = False) -> Dict:
    """Get summary of LLM health analysis."""
    try:
        return llm_analyzer.get_summary(force_refresh)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/quality/refresh-llm-analysis")
async def refresh_llm_analysis() -> Dict:
    """Manually refresh LLM analysis for all tools."""
    try:
        results = llm_analyzer.analyze_all_tools(force_refresh=True)
        return {
            "status": "completed",
            "analyzed": len(results),
            "summary": llm_analyzer.get_summary(force_refresh=False)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
