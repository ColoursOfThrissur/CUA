"""
Execution Supervisor

Monitors wave results mid-execution and decides whether to:
  - CONTINUE   — results look good, proceed normally
  - RETRY_STEP — re-run a specific failed step with an alternative tool
  - REPLAN     — regenerate remaining steps given what succeeded so far

Sits between waves in ExecutionEngine. Does NOT replace the planner —
it calls TaskPlanner.replan_remaining() to regenerate only the tail of
the plan, keeping completed steps intact.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from application.use_cases.execution.execution_engine import ExecutionState, StepResult, StepStatus
    from application.use_cases.planning.task_planner import TaskStep, ExecutionPlan

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supervisor decision
# ---------------------------------------------------------------------------

DECISION_CONTINUE    = "continue"
DECISION_RETRY_STEP  = "retry_step"
DECISION_REPLAN      = "replan"
DECISION_ABORT       = "abort"


@dataclass
class SupervisorDecision:
    action: str                              # continue | retry_step | replan | abort
    reason: str
    retry_step_id: Optional[str] = None     # which step to retry
    alt_tool: Optional[str] = None          # alternative tool for retry
    wait_seconds: float = 0.0               # optional delay before retry
    replan_context: Optional[Dict] = None   # extra context to pass to replanner
    confidence: float = 1.0


# ---------------------------------------------------------------------------
# Anomaly detection helpers
# ---------------------------------------------------------------------------

def _count_failed(wave_results: Dict[str, Any]) -> int:
    from application.use_cases.execution.execution_engine import StepStatus
    return sum(1 for r in wave_results.values() if r.status == StepStatus.FAILED)


def _failed_steps(wave_results: Dict[str, Any]) -> List[str]:
    from application.use_cases.execution.execution_engine import StepStatus
    return [sid for sid, r in wave_results.items() if r.status == StepStatus.FAILED]


def _all_failed(wave_results: Dict[str, Any]) -> bool:
    return _count_failed(wave_results) == len(wave_results)


def _feedback(result: Any) -> Dict[str, Any]:
    meta = getattr(result, "meta", {}) or {}
    return meta.get("execution_feedback", {}) or {}


def _advisory_steps(wave_results: Dict[str, Any]) -> List[str]:
    advisory_ids: List[str] = []
    for sid, result in wave_results.items():
        feedback = _feedback(result)
        if not feedback:
            continue
        action_status = str(feedback.get("action_status") or "")
        recommended = str(feedback.get("recommended_action") or "")
        if action_status in {"partial", "blocked_waiting", "needs_replan"} or recommended in {"replan", "insert_checkpoint", "verify_state"}:
            advisory_ids.append(sid)
    return advisory_ids


def _local_recovery_action(feedback: Dict[str, Any]) -> str:
    recommended = str(feedback.get("recommended_action") or "")
    action_status = str(feedback.get("action_status") or "")
    if recommended in {"wait_and_retry", "retry"}:
        return "retry_step"
    if action_status in {"partial", "blocked_waiting"} and recommended == "continue":
        return "retry_step"
    return "replan"


def _feedback_wait_seconds(feedback: Dict[str, Any]) -> float:
    try:
        return max(0.0, float(feedback.get("wait_seconds", 0.0) or 0.0))
    except Exception:
        return 0.0


def _critical_step_failed(failed_ids: List[str], remaining_steps: List[Any]) -> bool:
    """True if any failed step is a dependency of a remaining step."""
    remaining_deps = set()
    for step in remaining_steps:
        remaining_deps.update(step.dependencies)
    return bool(set(failed_ids) & remaining_deps)


# ---------------------------------------------------------------------------
# Supervisor
# ---------------------------------------------------------------------------

class ExecutionSupervisor:
    """
    Called after each wave completes. Analyses results and returns a
    SupervisorDecision that ExecutionEngine acts on.
    """

    def __init__(self, tool_registry=None, llm_client=None):
        self._registry = tool_registry
        self._llm = llm_client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def assess_wave(
        self,
        wave_results: Dict[str, Any],       # step_id → StepResult
        wave_steps: List[Any],              # TaskStep list for this wave
        remaining_steps: List[Any],         # TaskStep list not yet executed
        state: Any,                         # ExecutionState
        skill_context: Optional[Any] = None,
    ) -> SupervisorDecision:
        """
        Assess the outcome of a completed wave and decide what to do next.
        """
        failed_ids = _failed_steps(wave_results)
        advisory_ids = _advisory_steps(wave_results)

        # Nothing failed — continue
        if not failed_ids and not advisory_ids:
            return SupervisorDecision(action=DECISION_CONTINUE, reason="All wave steps succeeded.")

        # Advisory mismatch even though mechanics succeeded — adapt before continuing.
        if advisory_ids and not failed_ids:
            local_recovery = self._choose_local_recovery(advisory_ids, wave_results, wave_steps, state)
            if local_recovery:
                return local_recovery
            completed_summary = self._build_completed_summary(state)
            details = {
                sid: _feedback(wave_results[sid])
                for sid in advisory_ids
                if sid in wave_results
            }
            return SupervisorDecision(
                action=DECISION_REPLAN,
                reason=(
                    f"{len(advisory_ids)} step(s) completed with state mismatch or checkpoint advisory: "
                    f"{advisory_ids}. Replanning remaining work."
                ),
                replan_context={
                    "completed_summary": completed_summary,
                    "advisory_steps": advisory_ids,
                    "advisory_feedback": details,
                },
                confidence=0.75,
            )

        # Everything failed — abort if no remaining steps depend on anything else
        if _all_failed(wave_results) and not remaining_steps:
            return SupervisorDecision(
                action=DECISION_ABORT,
                reason=f"All {len(wave_results)} wave steps failed and no remaining steps.",
                confidence=0.95,
            )

        # Check if failed steps block remaining work
        blocks_remaining = _critical_step_failed(failed_ids, remaining_steps)

        if not blocks_remaining:
            # Failures are non-critical — continue, remaining steps are independent
            return SupervisorDecision(
                action=DECISION_CONTINUE,
                reason=f"{len(failed_ids)} step(s) failed but none block remaining work.",
                confidence=0.85,
            )

        # Failures block remaining steps — try to recover
        # Option 1: single failed step with an available alt tool → retry
        if len(failed_ids) == 1:
            step_id = failed_ids[0]
            failed_step = next((s for s in wave_steps if s.step_id == step_id), None)
            failed_feedback = _feedback(wave_results.get(step_id))
            if failed_step:
                retry_decision = self._build_same_step_retry_decision(
                    step=failed_step,
                    feedback=failed_feedback,
                    state=state,
                    reason_prefix="Critical step failed but feedback suggests local recovery",
                )
                if retry_decision:
                    return retry_decision
            alt = self._find_alt_tool(failed_step, state) if failed_step else None
            if alt:
                return SupervisorDecision(
                    action=DECISION_RETRY_STEP,
                    reason=f"Step {step_id} failed; retrying with alternative tool '{alt}'.",
                    retry_step_id=step_id,
                    alt_tool=alt,
                    confidence=0.80,
                )

        # Option 2: replan remaining steps
        completed_summary = self._build_completed_summary(state)
        return SupervisorDecision(
            action=DECISION_REPLAN,
            reason=(
                f"{len(failed_ids)} critical step(s) failed: {failed_ids}. "
                f"Replanning {len(remaining_steps)} remaining step(s)."
            ),
            replan_context={
                "completed_summary": completed_summary,
                "failed_steps": failed_ids,
                "failed_errors": {
                    sid: wave_results[sid].error
                    for sid in failed_ids
                    if sid in wave_results
                },
            },
            confidence=0.70,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_alt_tool(self, step: Any, state: Any) -> Optional[str]:
        """
        Find an alternative tool that covers the same operation with compatible parameters.
        Checks skill_context fallback_tools first, then registry.
        """
        # Check execution context fallback tools
        skill_ctx = getattr(state, "_skill_context", None)
        if skill_ctx and hasattr(skill_ctx, "fallback_tools"):
            for ft in skill_ctx.fallback_tools:
                if ft != step.tool_name:
                    return ft

        if not self._registry:
            return None

        # Required param names from the failing step
        required_params = set(step.parameters.keys())

        # Look for another loaded tool that has the same operation AND compatible params
        for tool in getattr(self._registry, "tools", []):
            if tool.__class__.__name__ == step.tool_name:
                continue
            caps = tool.get_capabilities() or {}
            if step.operation not in caps:
                continue
            # Check that the alt tool accepts all params the step provides
            alt_param_names = {p.name for p in caps[step.operation].parameters}
            if required_params <= alt_param_names:
                return tool.__class__.__name__

        return None

    def _choose_local_recovery(
        self,
        advisory_ids: List[str],
        wave_results: Dict[str, Any],
        wave_steps: List[Any],
        state: Any,
    ) -> Optional[SupervisorDecision]:
        """Prefer bounded same-step recovery before escalating to replanning."""
        for step_id in advisory_ids:
            step = next((s for s in wave_steps if s.step_id == step_id), None)
            if not step:
                continue
            decision = self._build_same_step_retry_decision(
                step=step,
                feedback=_feedback(wave_results.get(step_id)),
                state=state,
                reason_prefix="State mismatch appears transient",
            )
            if decision:
                return decision
        return None

    def _build_same_step_retry_decision(
        self,
        step: Any,
        feedback: Dict[str, Any],
        state: Any,
        reason_prefix: str,
    ) -> Optional[SupervisorDecision]:
        """Build a bounded retry decision when feedback indicates local recovery is worthwhile."""
        if _local_recovery_action(feedback) != "retry_step":
            return None

        max_attempts = self._max_local_recovery_attempts(step)
        attempts = getattr(state, "recovery_attempts", {}).get(step.step_id, 0)
        if attempts >= max_attempts:
            return None

        blocking_reason = feedback.get("blocking_reason") or "transient_state"
        return SupervisorDecision(
            action=DECISION_RETRY_STEP,
            reason=(
                f"{reason_prefix} for {step.step_id}; retrying same step "
                f"({attempts + 1}/{max_attempts}) due to {blocking_reason}."
            ),
            retry_step_id=step.step_id,
            alt_tool=None,
            wait_seconds=_feedback_wait_seconds(feedback),
            confidence=0.82,
        )

    def _max_local_recovery_attempts(self, step: Any) -> int:
        """Bound supervisor-level recovery so transient steps cannot loop forever."""
        retry_policy = getattr(step, "retry_policy", {}) or {}
        for key in ("max_attempts", "max_recovery_attempts", "supervisor_retries"):
            value = retry_policy.get(key)
            if value is None:
                continue
            try:
                return max(1, int(value))
            except Exception:
                continue
        return 2

    def _build_completed_summary(self, state: Any) -> Dict[str, Any]:
        """Summarise completed step outputs for the replanner."""
        registry = getattr(state, "state_registry", None)
        if registry is not None:
            summary = registry.build_completed_summary()
            if summary:
                return summary
        from application.use_cases.execution.execution_engine import StepStatus
        summary = {}
        for step_id, result in state.step_results.items():
            if result.status == StepStatus.COMPLETED:
                output = result.output
                # Truncate large outputs
                if isinstance(output, (dict, list)):
                    import json
                    text = json.dumps(output, default=str)
                    summary[step_id] = text[:400] + "..." if len(text) > 400 else text
                else:
                    summary[step_id] = str(output)[:400]
        return summary
