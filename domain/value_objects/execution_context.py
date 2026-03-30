"""
Skill Execution Context - Carries skill metadata through entire execution pipeline.

This context object is created after skill selection and flows through:
  Skill Selection → Tool Selection → Validation → Execution → Output Validation

It provides:
- Skill-aware tool selection (preferred tools, fallback strategies)
- Skill-aware validation (verification_mode, expected I/O types)
- Skill-aware recovery (max_retries, degraded_mode, circuit breaker awareness)
- Full execution tracing for observability
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid

from domain.entities.skill_models import SkillDefinition


@dataclass
class ToolVersion:
    """Tool version with health status."""
    name: str
    version: str
    healthy: bool
    circuit_breaker_state: str  # CLOSED, OPEN, HALF_OPEN


@dataclass
class SkillExecutionContext:
    """
    Execution context that flows through the entire request pipeline.
    Created after skill selection, carries skill metadata to guide execution.
    """
    
    # Core identification
    execution_id: str = field(default_factory=lambda: f"exec_{uuid.uuid4().hex[:12]}")
    skill_name: str = ""
    category: str = ""
    skill_definition: Optional[SkillDefinition] = None
    
    # Skill-derived execution guidance
    verification_mode: str = "output_validation"  # source_backed, side_effect_observed, output_validation
    risk_level: str = "medium"  # low, medium, high
    fallback_strategy: str = "fail_fast"  # fail_fast, direct_tool_routing, degraded_mode
    
    # Tool selection guidance
    preferred_tools: List[str] = field(default_factory=list)
    available_tools: Dict[str, ToolVersion] = field(default_factory=dict)
    selected_tool: Optional[str] = None
    fallback_tools: List[str] = field(default_factory=list)
    tool_selection_reasoning: str = ""
    
    # Input/Output expectations (from skill)
    expected_input_types: List[str] = field(default_factory=list)
    expected_output_types: List[str] = field(default_factory=list)
    
    # Recovery settings (derived from risk_level)
    max_retries: int = 3
    retry_backoff: float = 1.0  # seconds
    degraded_mode_enabled: bool = False
    
    # Execution state
    resolved_parameters: Dict[str, Any] = field(default_factory=dict)
    validation_rules: Dict[str, Any] = field(default_factory=dict)
    partial_results: List[Dict[str, Any]] = field(default_factory=list)
    step_history: List[Dict[str, Any]] = field(default_factory=list)
    errors_encountered: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    # Metrics
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None
    execution_time_seconds: float = 0.0
    retry_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize context for logging/tracing."""
        return {
            "execution_id": self.execution_id,
            "skill_name": self.skill_name,
            "category": self.category,
            "verification_mode": self.verification_mode,
            "risk_level": self.risk_level,
            "selected_tool": self.selected_tool,
            "fallback_tools": self.fallback_tools,
            "tool_selection_reasoning": self.tool_selection_reasoning,
            "resolved_parameters": self.resolved_parameters,
            "step_history": self.step_history,
            "errors_encountered": self.errors_encountered,
            "warnings": self.warnings,
            "execution_time_seconds": self.execution_time_seconds,
            "retry_count": self.retry_count,
        }
    
    def mark_complete(self):
        """Mark execution as complete and calculate duration."""
        self.end_time = datetime.utcnow()
        self.execution_time_seconds = (self.end_time - self.start_time).total_seconds()
    
    def add_step(self, tool: str, operation: str, status: str, duration: float, result: Any = None):
        """Record a step in execution history."""
        self.step_history.append({
            "tool": tool,
            "operation": operation,
            "status": status,
            "duration": duration,
            "result": result,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    def add_error(self, tool: str, error: str, retry_count: int):
        """Record an error for recovery logic."""
        self.errors_encountered.append({
            "tool": tool,
            "error": error,
            "retry_count": retry_count,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    def should_retry(self) -> bool:
        """Determine if execution should retry based on context."""
        return self.retry_count < self.max_retries and self.risk_level in ["low", "medium"]
    
    def should_fallback(self) -> bool:
        """Determine if execution should fallback to secondary tool."""
        return len(self.fallback_tools) > 0 and self.fallback_strategy == "direct_tool_routing"
    
    def should_degrade(self) -> bool:
        """Determine if execution should enter degraded mode."""
        return self.degraded_mode_enabled and self.fallback_strategy == "degraded_mode"
