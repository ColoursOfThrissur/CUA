"""Task domain entities - Pure business objects."""
from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class TaskStep:
    """Single step in execution plan."""
    step_id: str
    description: str
    tool_name: str
    operation: str
    parameters: Dict[str, Any]
    dependencies: List[str]
    expected_output: str
    domain: str = "general"
    retry_on_failure: bool = True
    max_retries: int = 3
    preconditions: List[str] = field(default_factory=list)
    postconditions: List[str] = field(default_factory=list)
    checkpoint_policy: str = "on_failure"
    retry_policy: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionPlan:
    """Complete execution plan for a goal."""
    goal: str
    steps: List[TaskStep]
    estimated_duration: int
    complexity: str
    requires_approval: bool = False
    
    def get_step(self, step_id: str) -> TaskStep | None:
        """Find step by ID."""
        return next((s for s in self.steps if s.step_id == step_id), None)
    
    def get_independent_steps(self) -> List[TaskStep]:
        """Get steps with no dependencies (can run in parallel)."""
        return [s for s in self.steps if not s.dependencies]
    
    def get_dependent_steps(self, step_id: str) -> List[TaskStep]:
        """Get steps that depend on given step."""
        return [s for s in self.steps if step_id in s.dependencies]
