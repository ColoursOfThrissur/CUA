"""Analyzer for tool evolution - combines observability + code."""
from pathlib import Path
from typing import Optional, Dict, Any
import logging
from core.tool_evolution_logger import get_evolution_logger

logger = logging.getLogger(__name__)
evo_logger = get_evolution_logger()


class ToolAnalyzer:
    """Analyzes tool using observability data + code."""
    
    def __init__(self, quality_analyzer):
        self.quality_analyzer = quality_analyzer
    
    def analyze_tool(self, tool_name: str, user_prompt: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Analyze tool combining observability and code."""
        logger.info(f"Analyzing {tool_name}")
        
        try:
            # Get observability data
            report = self.quality_analyzer.analyze_tool(tool_name)
            
            # Find tool file
            tool_path = self._find_tool_file(tool_name)
            if not tool_path:
                logger.error(f"Tool file not found: {tool_name}")
                return None
            
            # Read current code
            current_code = tool_path.read_text()
            
            logger.info(f"Analysis complete: health={report.health_score:.0f}")
            
            # Build analysis
            analysis = {
                "tool_name": tool_name,
                "tool_path": str(tool_path),
                "current_code": current_code,
                "health_score": report.health_score,
                "success_rate": report.success_rate,
                "issues": report.issues,
                "risk_score": report.avg_risk_score,
                "recommendation": report.recommendation,
                "user_prompt": user_prompt,
                "summary": self._build_summary(report, user_prompt)
            }
            
            return analysis
        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            return None
    
    def _build_summary(self, report, user_prompt):
        """Build human-readable summary."""
        if user_prompt:
            return f"User request: {user_prompt}. Current health: {report.health_score:.1f}/100"
        else:
            issues_str = ", ".join(report.issues[:3])
            return f"Health: {report.health_score:.1f}/100. Issues: {issues_str}"
    
    def _find_tool_file(self, tool_name: str) -> Optional[Path]:
        """Find tool file."""
        candidates = [
            Path(f"tools/{tool_name}.py"),
            Path(f"tools/{tool_name.lower()}.py"),
            Path(f"tools/experimental/{tool_name}.py"),
            Path(f"tools/test_tool.py") if "test" in tool_name.lower() else None,
        ]
        
        for path in candidates:
            if path and path.exists():
                logger.info(f"Found tool file: {path}")
                return path
        
        logger.error(f"Tool file not found for {tool_name}. Tried: {[str(c) for c in candidates if c]}")
        return None
