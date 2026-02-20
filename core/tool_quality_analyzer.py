"""Analyzes tool quality from execution logs."""
from dataclasses import dataclass
from typing import Dict, List

from core.tool_execution_logger import get_execution_logger


@dataclass
class ToolQualityReport:
    """Quality assessment for a tool."""
    tool_name: str
    success_rate: float
    usage_frequency: int
    avg_execution_time_ms: float
    output_richness: float
    avg_risk_score: float
    health_score: float
    issues: List[str]
    recommendation: str


class ToolQualityAnalyzer:
    """Analyzes tool performance and identifies weak tools."""
    
    # Quality thresholds
    MIN_SUCCESS_RATE = 0.7
    MIN_USAGE_FREQUENCY = 5
    MAX_EXECUTION_TIME_MS = 5000
    MIN_OUTPUT_SIZE = 10
    
    def __init__(self):
        self.logger = get_execution_logger()
    
    def analyze_tool(self, tool_name: str, days: int = 7) -> ToolQualityReport:
        """Analyze quality of a single tool."""
        stats = self.logger.get_tool_stats(tool_name, days)
        
        success_rate = stats["success_rate"]
        usage_frequency = stats["total_executions"]
        avg_time = stats["avg_time_ms"]
        avg_output = stats["avg_output_size"]
        avg_risk = stats.get("avg_risk_score", 0.0)
        
        # Calculate output richness (0-1 scale)
        output_richness = min(avg_output / 1000, 1.0) if avg_output > 0 else 0.0
        
        # Identify issues
        issues = []
        if success_rate < self.MIN_SUCCESS_RATE:
            issues.append(f"Low success rate: {success_rate:.1%}")
        if usage_frequency < self.MIN_USAGE_FREQUENCY:
            issues.append(f"Low usage: {usage_frequency} executions")
        if avg_time > self.MAX_EXECUTION_TIME_MS:
            issues.append(f"Slow execution: {avg_time:.0f}ms avg")
        if avg_output < self.MIN_OUTPUT_SIZE:
            issues.append(f"Minimal output: {avg_output:.0f} bytes avg")
        if avg_risk > 0.5:
            issues.append(f"High risk score: {avg_risk:.2f}")
        
        # Calculate health score (0-100) - risk reduces score
        health_score = (
            success_rate * 40 +  # 40% weight on success
            min(usage_frequency / 50, 1.0) * 30 +  # 30% weight on usage
            (1 - min(avg_time / 10000, 1.0)) * 15 +  # 15% weight on speed
            output_richness * 15  # 15% weight on output
        )
        # Reduce score based on risk
        health_score = health_score * (1 - avg_risk * 0.3)  # Risk can reduce score by up to 30%
        
        # Generate recommendation
        if health_score >= 80:
            recommendation = "HEALTHY"
        elif health_score >= 60:
            recommendation = "MONITOR"
        elif health_score >= 40:
            recommendation = "IMPROVE"
        else:
            recommendation = "QUARANTINE"
        
        return ToolQualityReport(
            tool_name=tool_name,
            success_rate=success_rate,
            usage_frequency=usage_frequency,
            avg_execution_time_ms=avg_time,
            output_richness=output_richness,
            avg_risk_score=avg_risk,
            health_score=health_score,
            issues=issues,
            recommendation=recommendation
        )
    
    def analyze_all_tools(self, days: int = 7, only_existing: bool = True) -> List[ToolQualityReport]:
        """Analyze all tools and return sorted by health score."""
        all_stats = self.logger.get_all_tools_stats(days)
        reports = []
        
        for tool_name in all_stats.keys():
            # Skip if tool file doesn't exist
            if only_existing and not self._tool_file_exists(tool_name):
                continue
            reports.append(self.analyze_tool(tool_name, days))
        
        return sorted(reports, key=lambda r: r.health_score)
    
    def _tool_file_exists(self, tool_name: str) -> bool:
        """Check if tool file exists."""
        from pathlib import Path
        candidates = [
            Path(f"tools/{tool_name}.py"),
            Path(f"tools/{tool_name.lower()}.py"),
            Path(f"tools/experimental/{tool_name}.py"),
        ]
        return any(p.exists() for p in candidates)
    
    def get_weak_tools(self, days: int = 7, min_usage: int = 5) -> List[ToolQualityReport]:
        """Get tools that need improvement (used enough to have data)."""
        reports = self.analyze_all_tools(days)
        return [
            r for r in reports 
            if r.usage_frequency >= min_usage and r.recommendation in ["IMPROVE", "QUARANTINE"]
        ]
    
    def get_summary(self, days: int = 7) -> Dict[str, any]:
        """Get overall tool ecosystem health summary."""
        reports = self.analyze_all_tools(days)
        
        if not reports:
            return {
                "total_tools": 0,
                "avg_health_score": 0.0,
                "healthy_tools": 0,
                "weak_tools": 0,
                "quarantine_tools": 0
            }
        
        return {
            "total_tools": len(reports),
            "avg_health_score": sum(r.health_score for r in reports) / len(reports),
            "healthy_tools": sum(1 for r in reports if r.recommendation == "HEALTHY"),
            "monitor_tools": sum(1 for r in reports if r.recommendation == "MONITOR"),
            "weak_tools": sum(1 for r in reports if r.recommendation == "IMPROVE"),
            "quarantine_tools": sum(1 for r in reports if r.recommendation == "QUARANTINE")
        }
