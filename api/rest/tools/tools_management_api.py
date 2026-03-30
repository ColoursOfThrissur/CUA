"""API endpoints for tools management page."""
from fastapi import APIRouter, HTTPException, Response
from typing import Dict, List
from pathlib import Path

from domain.services.tool_quality_analyzer import ToolQualityAnalyzer
from infrastructure.logging.tool_execution_logger import get_execution_logger
from infrastructure.analysis.llm_tool_health_analyzer import LLMToolHealthAnalyzer

router = APIRouter()
exec_logger = get_execution_logger()
analyzer = ToolQualityAnalyzer(exec_logger)
llm_analyzer = LLMToolHealthAnalyzer()


def add_cors_headers(response: Response):
    """Add CORS headers to response"""
    response.headers["Access-Control-Allow-Origin"] = "https://exquisite-quokka-08aa49.netlify.app"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response


@router.get("/tools-management/summary")
async def get_tools_summary(response: Response) -> Dict:
    """Get summary stats for all tools."""
    try:
        # Get all tool files
        all_tool_files = set()
        
        # Core tools
        for tool_file in Path("tools").glob("*_tool.py"):
            if tool_file.stem not in ['test_tool', 'test_web_content_extractor']:
                tool_name = ''.join(word.capitalize() for word in tool_file.stem.split('_'))
                all_tool_files.add(tool_name)
        
        # Experimental tools
        experimental_path = Path("tools/experimental")
        if experimental_path.exists():
            for tool_file in experimental_path.glob("*.py"):
                if not tool_file.stem.startswith('test_') and tool_file.stem != '__init__':
                    all_tool_files.add(tool_file.stem)
        
        # Get quality reports for tools with execution history
        all_reports = analyzer.analyze_all_tools(days=7)
        reports_dict = {r.tool_name: r for r in all_reports}
        
        # Count by status
        healthy = 0
        monitor = 0
        weak = 0
        broken = 0
        unknown = 0
        tools_with_errors = 0
        total_executions = 0
        
        for tool_name in all_tool_files:
            if tool_name in reports_dict:
                r = reports_dict[tool_name]
                if r.recommendation == "HEALTHY":
                    healthy += 1
                elif r.recommendation == "MONITOR":
                    monitor += 1
                elif r.recommendation == "IMPROVE":
                    weak += 1
                elif r.recommendation == "QUARANTINE":
                    broken += 1
                
                if r.has_recent_errors:
                    tools_with_errors += 1
                
                total_executions += r.usage_frequency
            else:
                unknown += 1
        
        result = {
            "total_tools": len(all_tool_files),
            "healthy_tools": healthy,
            "monitor_tools": monitor,
            "weak_tools": weak,
            "quarantine_tools": broken,
            "unknown_tools": unknown,
            "tools_with_errors": tools_with_errors,
            "total_executions": total_executions
        }
        
        add_cors_headers(response)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tools-management/list")
async def get_tools_list(response: Response, status_filter: str = None) -> List[Dict]:
    """Get list of all tools with health info."""
    try:
        # Get all tool files
        all_tool_files = set()
        
        # Core tools
        for tool_file in Path("tools").glob("*_tool.py"):
            if tool_file.stem not in ['test_tool', 'test_web_content_extractor']:
                tool_name = ''.join(word.capitalize() for word in tool_file.stem.split('_'))
                all_tool_files.add(tool_name)
        
        # Experimental tools
        experimental_path = Path("tools/experimental")
        if experimental_path.exists():
            for tool_file in experimental_path.glob("*.py"):
                if not tool_file.stem.startswith('test_') and tool_file.stem != '__init__':
                    all_tool_files.add(tool_file.stem)
        
        # Get quality reports for tools with execution history
        reports = analyzer.analyze_all_tools(days=7)
        reports_dict = {r.tool_name: r for r in reports}
        
        tools = []
        for tool_name in all_tool_files:
            if tool_name in reports_dict:
                r = reports_dict[tool_name]
                if status_filter and r.recommendation != status_filter:
                    continue
                tools.append({
                    "tool_name": r.tool_name,
                    "health_score": r.health_score,
                    "recommendation": r.recommendation,
                    "success_rate": r.success_rate,
                    "usage_frequency": r.usage_frequency,
                    "has_recent_errors": r.has_recent_errors,
                    "issues_count": len(r.issues)
                })
            else:
                # Tool exists but no execution history
                if status_filter:
                    continue
                tools.append({
                    "tool_name": tool_name,
                    "health_score": 0,
                    "recommendation": "UNKNOWN",
                    "success_rate": 0,
                    "usage_frequency": 0,
                    "has_recent_errors": False,
                    "issues_count": 0
                })
        
        # Sort: errors first, then by health score
        tools.sort(key=lambda t: (not t["has_recent_errors"], -t["health_score"]))
        
        add_cors_headers(response)
        return tools
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tools-management/detail/{tool_name}")
async def get_tool_detail(tool_name: str) -> Dict:
    """Get comprehensive tool details."""
    try:
        # Try to get quality report
        try:
            report = analyzer.analyze_tool(tool_name, days=7)
            has_history = True
        except:
            # Tool exists but no execution history
            has_history = False
            report = None
        
        # LLM analysis
        try:
            llm_analysis = llm_analyzer.analyze_tool(tool_name, force_refresh=False)
        except:
            llm_analysis = None
        
        # Tool info
        try:
            # Call the tool info endpoint directly
            from api.tool_info_api import get_tool_info as get_info_func
            tool_info = await get_info_func(tool_name)
        except Exception as e:
            print(f"Failed to get tool info for {tool_name}: {e}")
            tool_info = {"description": "N/A", "capabilities": []}
        
        if has_history and report:
            return {
                "tool_name": tool_name,
                "health_score": report.health_score,
                "recommendation": report.recommendation,
                "success_rate": report.success_rate,
                "usage_frequency": report.usage_frequency,
                "avg_execution_time_ms": report.avg_execution_time_ms,
                "output_richness": report.output_richness,
                "avg_risk_score": report.avg_risk_score,
                "issues": report.issues,
                "has_recent_errors": report.has_recent_errors,
                "description": tool_info.get("description", "N/A"),
                "capabilities": tool_info.get("capabilities", []),
                "llm_analysis": llm_analysis
            }
        else:
            return {
                "tool_name": tool_name,
                "health_score": 0,
                "recommendation": "UNKNOWN",
                "success_rate": 0,
                "usage_frequency": 0,
                "avg_execution_time_ms": 0,
                "output_richness": 0,
                "avg_risk_score": 0,
                "issues": ["No execution history"],
                "has_recent_errors": False,
                "description": tool_info.get("description", "N/A"),
                "capabilities": tool_info.get("capabilities", []),
                "llm_analysis": llm_analysis
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tools-management/executions/{tool_name}")
async def get_tool_executions(tool_name: str, limit: int = 10) -> List[Dict]:
    """Get recent executions for a tool."""
    try:
        executions = exec_logger.get_recent_executions(tool_name, limit)
        return executions if executions else []
    except Exception:
        return []


@router.get("/tools-management/code/{tool_name}")
async def get_tool_code(tool_name: str) -> Dict:
    """Get tool source code."""
    try:
        candidates = [
            Path(f"tools/{tool_name}.py"),
            Path(f"tools/{tool_name.lower()}.py"),
            Path(f"tools/experimental/{tool_name}.py"),
        ]
        
        for path in candidates:
            if path.exists():
                return {
                    "tool_name": tool_name,
                    "path": str(path),
                    "code": path.read_text()
                }
        
        raise HTTPException(status_code=404, detail="Tool file not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tools-management/trigger-check/{tool_name}")
async def trigger_health_check(tool_name: str) -> Dict:
    """Trigger LLM health check for a tool."""
    try:
        result = llm_analyzer.analyze_tool(tool_name, force_refresh=True)
        return {
            "status": "completed",
            "tool_name": tool_name,
            "analysis": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
