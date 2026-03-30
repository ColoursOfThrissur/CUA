"""Analyzer for tool evolution - uses LLM health analysis."""
import re
from pathlib import Path
from typing import Optional, Dict, Any
from infrastructure.persistence.sqlite.logging import get_logger
from infrastructure.logging.tool_evolution_logger import get_evolution_logger

logger = get_logger("analyzer")
evo_logger = get_evolution_logger()


class ToolAnalyzer:
    """Analyzes tool using LLM health analysis + runtime metrics."""
    
    def __init__(self, quality_analyzer):
        self.quality_analyzer = quality_analyzer
        from infrastructure.analysis.llm_tool_health_analyzer import LLMToolHealthAnalyzer
        self.llm_analyzer = LLMToolHealthAnalyzer()
    
    def analyze_tool(self, tool_name: str, user_prompt: Optional[str] = None, execution_context: Optional[Any] = None) -> Optional[Dict[str, Any]]:
        """Analyze tool using LLM health analysis (primary) + runtime metrics (secondary) + execution context."""
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
            
            # Adjust based on runtime success rate — only penalize if there IS usage data
            if runtime_report.usage_frequency > 0 and runtime_report.success_rate < 0.5:
                health_score = min(health_score, 50.0)
            
            # Block evolution only if tool is HEALTHY but has critically low success rate
            # (external factors like network/browser, not code bugs)
            # Do NOT block WEAK/NEEDS_IMPROVEMENT tools — those need evolution most
            if runtime_report.success_rate < 0.3 and runtime_report.usage_frequency > 5 and category == 'HEALTHY':
                logger.warning(f"Tool {tool_name} has critically low success rate ({runtime_report.success_rate:.1%}) with healthy code — likely external factors, skipping evolution")
                return None
            
            logger.info(f"Analysis complete: category={category}, health={health_score:.0f}")
            
            # Extract context-driven priorities if execution_context provided
            context_priorities = []
            # Always inject recent DB failure patterns — more reliable than execution_context
            for err in self._get_recent_failures(tool_name):
                context_priorities.append(f"Recent failure: {err}")
            if execution_context:
                # Prioritize errors from execution context
                errors = getattr(execution_context, 'errors_encountered', [])
                if errors:
                    context_priorities.append(f"Fix execution errors: {len(errors)} failures")
                    for err in errors[:3]:  # Top 3 errors
                        context_priorities.append(f"  - {err.get('error', 'Unknown error')}")
                
                # Prioritize verification failures
                verification_mode = getattr(execution_context, 'verification_mode', None)
                if verification_mode:
                    context_priorities.append(f"Ensure output matches {verification_mode} requirements")
                
                # Prioritize performance if slow
                exec_time = getattr(execution_context, 'execution_time_seconds', 0)
                if exec_time > 5.0:
                    context_priorities.append(f"Optimize performance (current: {exec_time:.1f}s)")
                
                # Prioritize retry issues
                retry_count = getattr(execution_context, 'retry_count', 0)
                if retry_count > 0:
                    context_priorities.append(f"Reduce retry failures (retries: {retry_count})")
            
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
                "capabilities": self._extract_capabilities(current_code),
                "context_priorities": context_priorities,  # NEW: Context-driven priorities
                # Store serializable execution context data instead of the object
                "execution_context_data": self._serialize_execution_context(execution_context) if execution_context else None
            }
            
            return analysis
        except Exception as e:
            logger.error(f"Analysis failed: {e}", exc_info=True)
            return None
    
    def _get_recent_failures(self, tool_name: str) -> list:
        """Query tool_executions.db for top 3 distinct recent error messages."""
        try:
            from infrastructure.persistence.sqlite.utils import safe_connect, safe_close
            conn = safe_connect("data/tool_executions.db")
            if not conn:
                return []
            cursor = conn.cursor()
            cursor.execute("""
                SELECT error FROM executions
                WHERE tool_name = ? AND success = 0 AND error IS NOT NULL
                ORDER BY timestamp DESC LIMIT 10
            """, (tool_name,))
            rows = cursor.fetchall()
            safe_close(conn)
            seen, out = set(), []
            for (err,) in rows:
                key = err[:80]
                if key not in seen:
                    seen.add(key)
                    out.append(err[:200])
                if len(out) >= 3:
                    break
            return out
        except Exception:
            return []

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
    
    def _serialize_execution_context(self, execution_context) -> Dict[str, Any]:
        """Serialize execution context to JSON-compatible format."""
        if not execution_context:
            return None
        
        try:
            return {
                "skill_name": getattr(execution_context, 'skill_name', None),
                "verification_mode": getattr(execution_context, 'verification_mode', None),
                "risk_level": getattr(execution_context, 'risk_level', None),
                "execution_time_seconds": getattr(execution_context, 'execution_time_seconds', 0),
                "retry_count": getattr(execution_context, 'retry_count', 0),
                "errors_encountered": getattr(execution_context, 'errors_encountered', []),
                "warnings": getattr(execution_context, 'warnings', []),
                "selected_tool": getattr(execution_context, 'selected_tool', None),
                "preferred_tools": getattr(execution_context, 'preferred_tools', []),
                "fallback_tools": getattr(execution_context, 'fallback_tools', []),
                "expected_output_types": getattr(execution_context, 'expected_output_types', []),
                "step_history": getattr(execution_context, 'step_history', []),
            }
        except Exception as e:
            logger.warning(f"Failed to serialize execution context: {e}")
            return {"serialization_error": str(e)}
    
    def _extract_capabilities(self, code: str) -> list:
        """Extract capability names from code."""
        caps = re.findall(r"name=['\"](\w+)['\"]", code)
        return caps if caps else []
    
    def _find_tool_file(self, tool_name: str) -> Optional[Path]:
        """Find tool file."""
        try:
            from application.use_cases.tool_lifecycle.tool_registry_manager import ToolRegistryManager
            resolved = ToolRegistryManager().resolve_source_file(tool_name)
            if resolved and resolved.exists():
                logger.info(f"Found tool file via registry: {resolved}")
                return resolved
        except Exception:
            pass

        snake_case = re.sub(r'(?<!^)(?=[A-Z])', '_', tool_name).lower()

        candidates = [
            # Exact-case first — avoids m_c_p_adapter_tool.py style mangling
            Path(f"tools/experimental/{tool_name}.py"),
            Path(f"tools/{tool_name}.py"),
            Path(f"tools/{tool_name.lower()}.py"),
            Path(f"tools/{snake_case}.py"),
            Path(f"tools/experimental/{tool_name.lower()}.py"),
            Path(f"tools/experimental/{snake_case}.py"),
        ]
        
        for path in candidates:
            if path and path.exists():
                logger.info(f"Found tool file: {path}")
                return path
        
        logger.error(f"Tool file not found for {tool_name}")
        return None
