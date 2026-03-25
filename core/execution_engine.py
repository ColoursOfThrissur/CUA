"""Execution Engine - Executes multi-step plans with state management."""
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from core.task_planner import ExecutionPlan, TaskStep
from core.verification_engine import get_verification_engine, VERDICT_RETRY, VERDICT_FALLBACK
from core.execution_supervisor import (
    ExecutionSupervisor, DECISION_CONTINUE, DECISION_RETRY_STEP, DECISION_REPLAN, DECISION_ABORT
)

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
    
    def __init__(self, tool_registry, tool_orchestrator=None, execution_logger=None, task_planner=None):
        self.tool_registry = tool_registry
        self.tool_orchestrator = tool_orchestrator
        self.execution_logger = execution_logger
        self.task_planner = task_planner
        self.active_executions: Dict[str, ExecutionState] = {}
        self._verifier = get_verification_engine()
        self._supervisor = ExecutionSupervisor(tool_registry=tool_registry)

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
        
        logger.info(f"[ENGINE] Starting execution {execution_id} — goal: '{plan.goal[:80]}'")
        
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
            # Build parallel execution waves
            waves = self._build_execution_waves(plan.steps)
            logger.info(f"[ENGINE] Waves: {len(waves)} wave(s), steps per wave: {[len(w) for w in waves]}")

            all_steps = list(plan.steps)
            executed_step_ids: set = set()
            wave_index = 0

            while wave_index < len(waves):
                wave = waves[wave_index]
                remaining_after = [
                    s for s in all_steps
                    if s.step_id not in executed_step_ids
                    and s.step_id not in {ws.step_id for ws in wave}
                ]

                if len(wave) == 1:
                    step = wave[0]
                    if not self._dependencies_met(step, state):
                        logger.warning(f"Skipping {step.step_id} - dependencies not met")
                        state.step_results[step.step_id].status = StepStatus.SKIPPED
                        executed_step_ids.add(step.step_id)
                        wave_index += 1
                        continue
                    state.current_step = step.step_id
                    result = self._execute_step(step, state, skill_context)
                    state.step_results[step.step_id] = result
                    executed_step_ids.add(step.step_id)

                    decision = self._supervisor.assess_wave(
                        {step.step_id: result}, wave, remaining_after, state, skill_context
                    )
                    wave_index = self._apply_supervisor_decision(
                        decision, wave, waves, wave_index, remaining_after,
                        all_steps, executed_step_ids, state, plan, pause_on_failure, skill_context
                    )
                    if wave_index < 0:
                        return state
                else:
                    eligible = [s for s in wave if self._dependencies_met(s, state)]
                    skipped_steps = [s for s in wave if s not in eligible]
                    for s in skipped_steps:
                        logger.warning(f"Skipping {s.step_id} - dependencies not met")
                        state.step_results[s.step_id].status = StepStatus.SKIPPED
                        executed_step_ids.add(s.step_id)

                    if eligible:
                        logger.info(f"[ENGINE] Running {len(eligible)} step(s) in parallel: {[s.step_id for s in eligible]}")
                        wave_results = self._execute_parallel(eligible, state, skill_context)
                        for step_id, result in wave_results.items():
                            state.step_results[step_id] = result
                            executed_step_ids.add(step_id)

                        # Wave-level verification
                        completed = {sid: r.output for sid, r in wave_results.items() if r.status == StepStatus.COMPLETED}
                        if completed:
                            tool_names = {s.step_id: s.tool_name for s in eligible}
                            operations = {s.step_id: s.operation for s in eligible}
                            vresults = self._verifier.verify_wave(completed, tool_names, operations, skill_context)
                            for step_id, vr in vresults.items():
                                if not vr.passed:
                                    logger.warning(f"[VERIFY] Wave step {step_id} failed verification: {vr.notes}")
                                    if vr.verdict in (VERDICT_RETRY, VERDICT_FALLBACK):
                                        state.step_results[step_id].status = StepStatus.FAILED
                                        state.step_results[step_id].error = f"Verification: {vr.notes}"

                        decision = self._supervisor.assess_wave(
                            wave_results, eligible, remaining_after, state, skill_context
                        )
                        wave_index = self._apply_supervisor_decision(
                            decision, eligible, waves, wave_index, remaining_after,
                            all_steps, executed_step_ids, state, plan, pause_on_failure, skill_context
                        )
                        if wave_index < 0:
                            return state
                    else:
                        wave_index += 1
            
            # Check overall success
            failed_steps = [r for r in state.step_results.values() if r.status == StepStatus.FAILED]
            if failed_steps:
                state.status = "completed_with_errors"
                state.error = f"{len(failed_steps)} steps failed"
            else:
                state.status = "completed"
            
            logger.info(f"[ENGINE] Execution {execution_id} finished: {state.status}")
            
        except Exception as e:
            logger.error(f"Execution {execution_id} failed: {e}")
            state.status = "failed"
            state.error = str(e)
        
        finally:
            state.end_time = time.time()
            state.current_step = None
            self._evict_executions()
        
        return state

    _MAX_ACTIVE_EXECUTIONS = 50  # keep last N completed executions for inspection

    def _evict_executions(self) -> None:
        """Evict oldest completed executions to prevent unbounded memory growth."""
        if len(self.active_executions) <= self._MAX_ACTIVE_EXECUTIONS:
            return
        finished = [
            (eid, s) for eid, s in self.active_executions.items()
            if s.status not in ("running", "paused")
        ]
        # Sort by end_time ascending — evict oldest first
        finished.sort(key=lambda x: x[1].end_time or 0)
        for eid, _ in finished[:len(finished) - self._MAX_ACTIVE_EXECUTIONS // 2]:
            del self.active_executions[eid]
    
    def _apply_supervisor_decision(
        self,
        decision,
        wave: List[TaskStep],
        waves: List[List[TaskStep]],
        wave_index: int,
        remaining_after: List[TaskStep],
        all_steps: List[TaskStep],
        executed_step_ids: set,
        state: "ExecutionState",
        plan: ExecutionPlan,
        pause_on_failure: bool,
        skill_context: Optional[Any] = None,
    ) -> int:
        """
        Act on a SupervisorDecision. Returns the next wave_index to use.
        Returns -1 to signal the caller to return state immediately (paused/aborted).
        """
        if decision.action == DECISION_CONTINUE:
            return wave_index + 1

        logger.info(f"[SUPERVISOR] {decision.action}: {decision.reason}")

        if decision.action == DECISION_ABORT:
            state.status = "failed"
            state.error = decision.reason
            return -1

        if decision.action == DECISION_RETRY_STEP and decision.retry_step_id and decision.alt_tool:
            # Swap tool on the failed step and re-insert it as a new single-step wave
            original = next((s for s in all_steps if s.step_id == decision.retry_step_id), None)
            if original:
                retry_step = TaskStep(
                    step_id=original.step_id,
                    description=f"{original.description} [retry with {decision.alt_tool}]",
                    tool_name=decision.alt_tool,
                    operation=original.operation,
                    parameters=original.parameters,
                    dependencies=original.dependencies,
                    expected_output=original.expected_output,
                    domain=original.domain,
                    retry_on_failure=False,  # already retrying
                    max_retries=1,
                )
                # Reset step result so it can run again
                state.step_results[original.step_id] = StepResult(
                    step_id=original.step_id, status=StepStatus.PENDING
                )
                executed_step_ids.discard(original.step_id)
                # Insert retry wave right after current position
                waves.insert(wave_index + 1, [retry_step])
                logger.info(f"[SUPERVISOR] Inserted retry wave for {original.step_id} with {decision.alt_tool}")
            return wave_index + 1

        if decision.action == DECISION_REPLAN and self.task_planner and remaining_after:
            try:
                # Forward skill context so replan uses filtered tools
                replan_ctx = decision.replan_context or {}
                if skill_context and hasattr(skill_context, 'preferred_tools'):
                    replan_ctx = dict(replan_ctx)
                    replan_ctx.setdefault("skill_context", {
                        "preferred_tools": list(skill_context.preferred_tools),
                        "skill_name": getattr(skill_context, 'skill_name', ''),
                    })
                # Inject completed step outputs so replanner can reference {{step_X}} results
                completed_outputs = {
                    sid: r.output
                    for sid, r in state.step_results.items()
                    if r.status == StepStatus.COMPLETED and r.output is not None
                }
                if completed_outputs:
                    replan_ctx = dict(replan_ctx)
                    replan_ctx["completed_summary"] = completed_outputs
                new_steps = self.task_planner.replan_remaining(
                    original_goal=plan.goal,
                    remaining_steps=remaining_after,
                    replan_context=replan_ctx,
                    context=replan_ctx,
                )
                if new_steps:
                    # Register new steps in state
                    for s in new_steps:
                        if s.step_id not in state.step_results:
                            state.step_results[s.step_id] = StepResult(
                                step_id=s.step_id, status=StepStatus.PENDING
                            )
                    # Replace remaining waves with new plan
                    new_waves = self._build_execution_waves(new_steps)
                    # Truncate waves list to current position + 1, then append new waves
                    del waves[wave_index + 1:]
                    waves.extend(new_waves)
                    # Update all_steps
                    all_steps[len(all_steps):] = [
                        s for s in new_steps if s.step_id not in {x.step_id for x in all_steps}
                    ]
                    logger.info(f"[SUPERVISOR] Replan inserted {len(new_waves)} new wave(s)")
            except Exception as e:
                logger.error(f"[SUPERVISOR] Replan failed: {e}")

        if pause_on_failure:
            state.status = "paused"
            return -1

        return wave_index + 1

    def _build_execution_waves(self, steps: List[TaskStep]) -> List[List[TaskStep]]:
        """Group steps into parallel waves. Steps in the same wave have no inter-dependencies."""
        step_map = {s.step_id: s for s in steps}
        completed: set = set()
        waves: List[List[TaskStep]] = []
        remaining = list(steps)

        while remaining:
            wave = [s for s in remaining if all(d in completed for d in s.dependencies)]
            if not wave:
                # Cycle guard — shouldn't happen after _validate_dependencies, but be safe
                raise ValueError("Circular dependency or unresolvable dependency in plan")
            waves.append(wave)
            for s in wave:
                completed.add(s.step_id)
                remaining.remove(s)

        return waves

    _STEP_TIMEOUT_S = 120  # max seconds a single parallel step may run

    def _execute_parallel(self, steps: List[TaskStep], state: ExecutionState, skill_context: Optional[Any]) -> Dict[str, StepResult]:
        """Execute a list of independent steps concurrently using a thread pool."""
        results: Dict[str, StepResult] = {}
        with ThreadPoolExecutor(max_workers=min(len(steps), 4)) as executor:
            future_to_step = {
                executor.submit(self._execute_step, step, state, skill_context): step
                for step in steps
            }
            for future in as_completed(future_to_step):
                step = future_to_step[future]
                try:
                    results[step.step_id] = future.result(timeout=self._STEP_TIMEOUT_S)
                except TimeoutError:
                    logger.error(f"Parallel step {step.step_id} timed out after {self._STEP_TIMEOUT_S}s")
                    results[step.step_id] = StepResult(
                        step_id=step.step_id,
                        status=StepStatus.FAILED,
                        error=f"Step timed out after {self._STEP_TIMEOUT_S}s"
                    )
                except Exception as e:
                    logger.error(f"Parallel step {step.step_id} raised: {e}")
                    results[step.step_id] = StepResult(
                        step_id=step.step_id,
                        status=StepStatus.FAILED,
                        error=str(e)
                    )
        return results

    def _execute_step(self, step: TaskStep, state: ExecutionState, skill_context: Optional[Any] = None) -> StepResult:
        """Execute a single step with retry logic."""
        logger.info(f"[ENGINE] Step {step.step_id}: {step.tool_name}.{step.operation}")
        
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

        # Emit step status to UI
        try:
            from core.event_bus import get_event_bus
            get_event_bus().emit_sync("agent_step_update", {
                "step_id": step.step_id,
                "status": result.status.value,
                "error": result.error,
            })
        except Exception:
            pass
        
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
        """Resolve {{step_X}} references — pass actual objects, only stringify when needed."""
        import re
        resolved = {}

        for key, value in params.items():
            if not isinstance(value, str):
                resolved[key] = value
                continue

            template_match = re.match(r'[\{\$]\{?(step_\d+)(?:[_\.]?(\w+))?\}?\}?', value)
            if not template_match:
                resolved[key] = value
                continue

            step_id = template_match.group(1)
            field = template_match.group(2)

            if step_id not in state.step_results:
                raise ValueError(f"Referenced step not found: {step_id}")

            step_result = state.step_results[step_id]
            if step_result.status == StepStatus.SKIPPED:
                raise ValueError(f"Referenced step was skipped (invalid tool/op): {step_id}")
            if step_result.status != StepStatus.COMPLETED:
                raise ValueError(f"Referenced step not completed: {step_id} (status: {step_result.status.value})")

            output = step_result.output

            if field and isinstance(output, dict) and field in output:
                resolved[key] = output[field]  # pass actual object, not stringified
            elif field in ('output', 'expected_output') or not field:
                resolved[key] = output
            elif isinstance(output, dict):
                for fallback_key in ('content', 'text', 'summary', 'results', 'data'):
                    if fallback_key in output:
                        resolved[key] = output[fallback_key]
                        break
                else:
                    resolved[key] = output  # pass full dict, let tool handle it
            else:
                resolved[key] = output

        return resolved
    
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
        """Resume a paused execution, respecting the original wave structure."""
        state = self.active_executions.get(execution_id)
        if not state or state.status != "paused":
            raise ValueError(f"Cannot resume execution {execution_id}")

        state.status = "running"

        remaining_steps = [
            step for step in state.plan.steps
            if state.step_results[step.step_id].status in (StepStatus.PENDING, StepStatus.FAILED)
        ]

        try:
            waves = self._build_execution_waves(remaining_steps)
            for wave in waves:
                eligible = [s for s in wave if self._dependencies_met(s, state)]
                if len(eligible) == 1:
                    result = self._execute_step(eligible[0], state)
                    state.step_results[eligible[0].step_id] = result
                elif eligible:
                    wave_results = self._execute_parallel(eligible, state, None)
                    for step_id, result in wave_results.items():
                        state.step_results[step_id] = result

            failed = [r for r in state.step_results.values() if r.status == StepStatus.FAILED]
            state.status = "completed_with_errors" if failed else "completed"
        except Exception as e:
            logger.error(f"Resume {execution_id} failed: {e}")
            state.status = "failed"
            state.error = str(e)
        finally:
            state.end_time = time.time()

        return state
