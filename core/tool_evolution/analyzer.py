"""Analyzer for tool evolution - uses LLM health analysis."""
from pathlib import Path
from typing import Optional, Dict, Any
from core.sqlite_logging import get_logger
from core.tool_evolution_logger import get_evolution_logger

logger = get_logger("analyzer")
evo_logger = get_evolution_logger()


class ToolAnalyzer:
    """Analyzes tool using LLM health analysis + runtime metrics."""
    
    def __init__(self, quality_analyzer):
        self.quality_analyzer = quality_analyzer
        from core.llm_tool_health_analyzer import LLMToolHealthAnalyzer
        self.llm_analyzer = LLMToolHealthAnalyzer()
    
    def analyze_tool(self, tool_name: str, user_prompt: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Analyze tool using LLM health analysis (primary) + runtime metrics (secondary)."""
        logger.info(f"Analyzing {tool_name}")
        
        try:
            # Find tool file
            tool_path = self._find_tool_file(tool_name)
            if not tool_path:
                logger.error(f"Tool file not found: {tool_name}")
                return None
            
            # Read current code
            current_code = tool_path.read_text()
            
            # Get LLM health analysis (primary source) - always use fresh data
            llm_report = self.llm_analyzer.analyze_tool(tool_name, force_refresh=True)
            
            # Get runtime metrics (secondary - for usage data)
            runtime_report = self.quality_analyzer.analyze_tool(tool_name)
            
            # Extract issues from LLM analysis
            llm_issues = []
            for issue in llm_report.get('issues', []):
                if isinstance(issue, dict):
                    severity = issue.get('severity', 'MEDIUM')
                    desc = issue.get('description', '')
                    llm_issues.append(f"[{severity}] {desc}")
            
            # Combine with runtime issues
            all_issues = llm_issues + runtime_report.issues
            
            # Calculate combined health score (LLM category + runtime metrics)
            category = llm_report.get('category', 'UNKNOWN')
            if category == 'WEAK':
                health_score = 40.0
            elif category == 'NEEDS_IMPROVEMENT':
                health_score = 60.0
            elif category == 'HEALTHY_WITH_MINOR_ISSUES':
                health_score = 80.0
            elif category == 'HEALTHY':
                health_score = 95.0
            else:
                health_score = runtime_report.health_score
            
            # Adjust based on runtime success rate
            if runtime_report.success_rate < 0.5:
                health_score = min(health_score, 50.0)
            
            # CRITICAL: Block evolution if tool is fundamentally broken
            # Low success rate with healthy code = external factors (network, browser)
            # But critically low success rate = broken tool regardless of code quality
            if runtime_report.success_rate < 0.3 and runtime_report.usage_frequency > 5:
                logger.error(f"Tool {tool_name} has critically low success rate ({runtime_report.success_rate:.1%}) - blocking evolution")
                logger.error("Tool may need manual inspection or redesign, not automated evolution")
                return None
            
            logger.info(f"Analysis complete: category={category}, health={health_score:.0f}")
            
            # Build analysis
            analysis = {
                "tool_name": tool_name,
                "tool_path": str(tool_path),
                "current_code": current_code,
                "health_score": health_score,
                "code_quality_category": category,
                "success_rate": runtime_report.success_rate,
                "usage_frequency": runtime_report.usage_frequency,
                "issues": all_issues,
                "llm_issues": llm_report.get('issues', []),
                "llm_improvements": llm_report.get('improvements', []),
                "risk_score": runtime_report.avg_risk_score,
                "recommendation": self._get_recommendation(category, runtime_report),
                "user_prompt": user_prompt,
                "summary": self._build_summary(category, health_score, all_issues, user_prompt),
                "capabilities": self._extract_capabilities(current_code)
            }
            
            return analysis
        except Exception as e:
            logger.error(f"Analysis failed: {e}", exc_info=True)
            return None
    
    def _get_recommendation(self, category: str, runtime_report) -> str:
        """Get evolution recommendation based on LLM category and runtime."""
        if category == 'WEAK':
            return 'EVOLVE_URGENT'
        elif category == 'NEEDS_IMPROVEMENT':
            return 'EVOLVE_RECOMMENDED'
        elif runtime_report.success_rate < 0.7:
            return 'EVOLVE_RECOMMENDED'
        elif category == 'HEALTHY_WITH_MINOR_ISSUES':
            return 'MONITOR'
        else:
            return 'HEALTHY'
    
    def _build_summary(self, category: str, health_score: float, issues: list, user_prompt: str) -> str:
        """Build human-readable summary."""
        if user_prompt:
            return f"User request: {user_prompt}. Code quality: {category}, Health: {health_score:.0f}/100"
        else:
            issue_count = len(issues)
            if issue_count == 0:
                return f"Code quality: {category}, Health: {health_score:.0f}/100. No issues found."
            else:
                issues_preview = ", ".join(issues[:2])
                return f"Code quality: {category}, Health: {health_score:.0f}/100. {issue_count} issues: {issues_preview}"
    
    def _extract_capabilities(self, code: str) -> list:
        """Extract capability names from code."""
        import re
        caps = re.findall(r"name=['\"](\w+)['\"]", code)
        return caps if caps else []
    
    def _find_tool_file(self, tool_name: str) -> Optional[Path]:
        """Find tool file."""
        try:
            from core.tool_registry_manager import ToolRegistryManager
            resolved = ToolRegistryManager().resolve_source_file(tool_name)
            if resolved and resolved.exists():
                logger.info(f"Found tool file via registry: {resolved}")
                return resolved
        except Exception:
            pass

        import re
        snake_case = re.sub(r'(?<!^)(?=[A-Z])', '_', tool_name).lower()
        
        candidates = [
            Path(f"tools/{tool_name}.py"),
            Path(f"tools/{tool_name.lower()}.py"),
            Path(f"tools/{snake_case}.py"),
            Path(f"tools/experimental/{tool_name}.py"),
            Path(f"tools/experimental/{tool_name.lower()}.py"),
            Path(f"tools/experimental/{snake_case}.py"),
        ]
        
        for path in candidates:
            if path and path.exists():
                logger.info(f"Found tool file: {path}")
                return path
        
        logger.error(f"Tool file not found for {tool_name}")
        return None
