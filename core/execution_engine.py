"""Execution Engine - Executes multi-step plans with state management."""
import logging
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from core.task_planner import ExecutionPlan, TaskStep

logger = logging.getLogger(__name__)


class StepStatus(Enum):
    """Status of execution step."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StepResult:
    """Result of executing a step."""
    step_id: str
    status: StepStatus
    output: Any = None
    error: Optional[str] = None
    execution_time: float = 0.0
    retry_count: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ExecutionState:
    """Current state of plan execution."""
    plan: ExecutionPlan
    step_results: Dict[str, StepResult] = field(default_factory=dict)
    current_step: Optional[str] = None
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    status: str = "running"  # running, completed, failed, paused
    error: Optional[str] = None


class ExecutionEngine:
    """Executes multi-step plans with error recovery."""
    
    def __init__(self, tool_registry, tool_orchestrator=None, execution_logger=None):
        self.tool_registry = tool_registry
        self.tool_orchestrator = tool_orchestrator
        self.execution_logger = execution_logger
        self.active_executions: Dict[str, ExecutionState] = {}
        
        # Initialize error recovery
        from core.error_recovery import ErrorRecovery, RecoveryConfig, RecoveryStrategy
        self.error_recovery = ErrorRecovery(RecoveryConfig(
            max_retries=3,
            initial_delay=1.0,
            backoff_factor=2.0,
            strategy=RecoveryStrategy.RETRY
        ))
    
    def execute_plan(
        self,
        plan: ExecutionPlan,
        execution_id: Optional[str] = None,
        pause_on_failure: bool = False,
        skill_context: Optional[Any] = None
    ) -> ExecutionState:
        """
        Execute a complete plan.
        
        Args:
            plan: ExecutionPlan to execute
            execution_id: Optional ID for tracking
            pause_on_failure: If True, pause instead of failing
        
        Returns:
            ExecutionState with results
        """
        if not execution_id:
            execution_id = f"exec_{int(time.time())}"
        
        logger.info(f"Starting execution {execution_id} for goal: {plan.goal}")
        
        # Initialize execution state
        state = ExecutionState(plan=plan)
        self.active_executions[execution_id] = state
        
        # Initialize all steps as pending
        for step in plan.steps:
            state.step_results[step.step_id] = StepResult(
                step_id=step.step_id,
                status=StepStatus.PENDING
            )
        
        try:
            # Execute steps in dependency order
            execution_order = self._get_execution_order(plan.steps)
            
            for step in execution_order:
                # Check if dependencies completed successfully
                if not self._dependencies_met(step, state):
                    logger.warning(f"Skipping {step.step_id} - dependencies not met")
                    state.step_results[step.step_id].status = StepStatus.SKIPPED
                    continue
                
                # Execute step
                state.current_step = step.step_id
                result = self._execute_step(step, state, skill_context)
                state.step_results[step.step_id] = result
                
                # Handle failure
                if result.status == StepStatus.FAILED:
                    if pause_on_failure:
                        state.status = "paused"
                        logger.warning(f"Execution paused at {step.step_id}")
                        return state
                    else:
                        # Continue to next step (non-critical failure)
                        logger.warning(f"Step {step.step_id} failed, continuing...")
            
            # Check overall success
            failed_steps = [r for r in state.step_results.values() if r.status == StepStatus.FAILED]
            if failed_steps:
                state.status = "completed_with_errors"
                state.error = f"{len(failed_steps)} steps failed"
            else:
                state.status = "completed"
            
            logger.info(f"Execution {execution_id} completed: {state.status}")
            
        except Exception as e:
            logger.error(f"Execution {execution_id} failed: {e}")
            state.status = "failed"
            state.error = str(e)
        
        finally:
            state.end_time = time.time()
            state.current_step = None
        
        return state
    
    def _execute_step(self, step: TaskStep, state: ExecutionState, skill_context: Optional[Any] = None) -> StepResult:
        """Execute a single step with retry logic."""
        logger.info(f"Executing step: {step.step_id} - {step.description}")
        
        result = StepResult(step_id=step.step_id, status=StepStatus.RUNNING)
        start_time = time.time()
        
        # Use skill context max_retries if available
        max_retries = step.max_retries if step.retry_on_failure else 1
        if skill_context and hasattr(skill_context, 'max_retries'):
            max_retries = skill_context.max_retries
        
        # Resolve parameters (may reference previous step outputs)
        try:
            resolved_params = self._resolve_parameters(step.parameters, state)
        except Exception as e:
            result.status = StepStatus.FAILED
            result.error = f"Parameter resolution failed: {e}"
            logger.error(f"Parameter resolution error for {step.step_id}: {e}")
            return result
        
        # Get tool instance
        tool = None
        for tool_instance in getattr(self.tool_registry, 'tools', []):
            if tool_instance.__class__.__name__ == step.tool_name:
                tool = tool_instance
                break
        
        if not tool:
            result.status = StepStatus.FAILED
            result.error = f"Tool not found: {step.tool_name}"
            return result
        
        # Execute with retries using orchestrator if available
        last_error = None
        for attempt in range(max_retries):
            try:
                # Use orchestrator if available for consistent execution
                if self.tool_orchestrator:
                    orchestrated_result = self.tool_orchestrator.execute_tool_step(
                        tool=tool,
                        tool_name=step.tool_name,
                        operation=step.operation,
                        parameters=resolved_params,
                        execution_context=skill_context
                    )
                    
                    if orchestrated_result.success:
                        result.status = StepStatus.COMPLETED
                        result.output = orchestrated_result.data
                        result.retry_count = attempt
                        break
                    else:
                        last_error = orchestrated_result.error
                else:
                    # Fallback to direct registry execution
                    tool_result = self.tool_registry.execute_capability(
                        step.operation,
                        **resolved_params
                    )
                    
                    # Check result
                    if tool_result.status.value == "success":
                        result.status = StepStatus.COMPLETED
                        result.output = tool_result.data
                        result.retry_count = attempt
                        break
                    else:
                        last_error = tool_result.error_message
                
                if attempt < max_retries - 1:
                    logger.warning(f"Step {step.step_id} attempt {attempt + 1} failed, retrying...")
                    backoff = skill_context.retry_backoff if skill_context and hasattr(skill_context, 'retry_backoff') else 1.0
                    time.sleep(backoff)
                    
            except Exception as e:
                last_error = str(e)
                if attempt < max_retries - 1:
                    logger.warning(f"Step {step.step_id} attempt {attempt + 1} error: {e}, retrying...")
                    backoff = skill_context.retry_backoff if skill_context and hasattr(skill_context, 'retry_backoff') else 1.0
                    time.sleep(backoff)
        
        # If all retries failed
        if result.status != StepStatus.COMPLETED:
            result.status = StepStatus.FAILED
            result.error = last_error or "Unknown error"
            logger.error(f"Step {step.step_id} failed after {max_retries} attempts: {result.error}")
        
        result.execution_time = time.time() - start_time
        
        # Log execution
        if self.execution_logger:
            self.execution_logger.log_step_execution(
                step_id=step.step_id,
                tool_name=step.tool_name,
                operation=step.operation,
                status=result.status.value,
                execution_time=result.execution_time,
                error=result.error
            )
        
        return result
    
    def _resolve_parameters(self, params: Dict[str, Any], state: ExecutionState) -> Dict[str, Any]:
        """Resolve parameters that reference previous step outputs with validation."""
        import re
        resolved = {}
        
        for key, value in params.items():
            # Handle {{step_X}}, ${step_X}, $step.step_X formats
            if isinstance(value, str):
                # Check for {{step_X_output}}, {{step_X.field}}, ${step_X.field} formats
                template_match = re.match(r'[\{\$]\{?(step_\d+)(?:[_\.]?(\w+))?\}?\}?', value)
                if template_match:
                    step_id = template_match.group(1)
                    field = template_match.group(2)
                    
                    if step_id not in state.step_results:
                        raise ValueError(f"Referenced step not found: {step_id}")
                    
                    step_result = state.step_results[step_id]
                    if step_result.status != StepStatus.COMPLETED:
                        raise ValueError(f"Referenced step not completed: {step_id} (status: {step_result.status.value})")
                    
                    output = step_result.output
                    
                    # Get field from output or use entire output
                    if field and isinstance(output, dict) and field in output:
                        resolved[key] = output[field]
                    elif field in ['output', 'expected_output'] or not field:
                        # Use entire output if 'output'/'expected_output' requested or no field specified
                        resolved[key] = output
                    elif isinstance(output, dict):
                        raise ValueError(f"Field '{field}' not found in {step_id} output. Available: {list(output.keys())}")
                    else:
                        resolved[key] = output
                    continue
            
            resolved[key] = value
        
        return resolved
    
    def _get_execution_order(self, steps: List[TaskStep]) -> List[TaskStep]:
        """Order steps by dependencies (topological sort)."""
        # Build dependency graph
        graph = {step.step_id: step for step in steps}
        in_degree = {step.step_id: len(step.dependencies) for step in steps}
        
        # Find steps with no dependencies
        queue = [step for step in steps if len(step.dependencies) == 0]
        ordered = []
        
        while queue:
            # Process step with no remaining dependencies
            current = queue.pop(0)
            ordered.append(current)
            
            # Reduce in-degree for dependent steps
            for step in steps:
                if current.step_id in step.dependencies:
                    in_degree[step.step_id] -= 1
                    if in_degree[step.step_id] == 0:
                        queue.append(step)
        
        if len(ordered) != len(steps):
            raise ValueError("Circular dependency detected in execution plan")
        
        return ordered
    
    def _dependencies_met(self, step: TaskStep, state: ExecutionState) -> bool:
        """Check if all dependencies completed successfully."""
        for dep_id in step.dependencies:
            if dep_id not in state.step_results:
                return False
            
            dep_result = state.step_results[dep_id]
            if dep_result.status != StepStatus.COMPLETED:
                return False
        
        return True
    
    def get_execution_state(self, execution_id: str) -> Optional[ExecutionState]:
        """Get current state of an execution."""
        return self.active_executions.get(execution_id)
    
    def pause_execution(self, execution_id: str) -> bool:
        """Pause an active execution."""
        state = self.active_executions.get(execution_id)
        if state and state.status == "running":
            state.status = "paused"
            return True
        return False
    
    def resume_execution(self, execution_id: str) -> ExecutionState:
        """Resume a paused execution."""
        state = self.active_executions.get(execution_id)
        if not state or state.status != "paused":
            raise ValueError(f"Cannot resume execution {execution_id}")
        
        state.status = "running"
        
        # Continue from current step
        remaining_steps = [
            step for step in state.plan.steps
            if state.step_results[step.step_id].status in [StepStatus.PENDING, StepStatus.FAILED]
        ]
        
        # Re-execute remaining steps
        for step in remaining_steps:
            if self._dependencies_met(step, state):
                result = self._execute_step(step, state)
                state.step_results[step.step_id] = result
        
        state.status = "completed"
        state.end_time = time.time()
        
        return state
