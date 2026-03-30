from types import SimpleNamespace

from application.use_cases.autonomy.execution_supervisor import (
    DECISION_REPLAN,
    DECISION_RETRY_STEP,
    ExecutionSupervisor,
    SupervisorDecision,
)
from application.state.state_registry import StateRegistry
from application.use_cases.execution.execution_engine import ExecutionEngine, ExecutionState, StepResult, StepStatus
from application.use_cases.execution.result_interpreter import ResultInterpreter
from application.use_cases.tool_lifecycle.tool_orchestrator import ToolOrchestrator
from domain.entities.task import ExecutionPlan, TaskStep


def test_result_interpreter_builds_planner_signal_and_artifacts():
    interpreter = ResultInterpreter()

    interpretation = interpreter.interpret(
        raw_result={"success": True},
        data={
            "success": True,
            "readiness": "loading",
            "path": "output/report.txt",
            "observed_after": {"title": "Steam"},
            "content": "partial output",
        },
        success=True,
        error=None,
        tool_name="ScreenPerceptionTool",
        operation="extract_text",
    )

    assert interpretation.artifacts[0]["path"] == "output/report.txt"
    assert interpretation.execution_feedback["recommended_action"] == "wait_and_retry"
    assert interpretation.planner_signal["tool_name"] == "ScreenPerceptionTool"
    assert interpretation.planner_signal["world_state"]["readiness"] == "loading"


def test_state_registry_builds_planner_context_from_recorded_steps():
    registry = StateRegistry()
    registry.record_step(
        step_id="step_1",
        tool_name="WebAccessTool",
        operation="fetch_page",
        status="completed",
        output={"text": "hello world"},
        artifacts=[{"type": "file_ref", "path": "output/page.txt"}],
        feedback={"world_state": {"page_title": "Example", "readiness": "ready"}},
        planner_signal={"output_summary": "Fetched example page"},
        resolved_parameters={"url": "https://example.com"},
        execution_time=0.4,
    )

    context = registry.build_planner_context()

    assert context["completed_summary"]["step_1"] == "Fetched example page"
    assert context["completed_artifacts"]["step_1"]["kind"] == "structured"
    assert context["latest_world_state"]["page_title"] == "Example"


def test_tool_orchestrator_extracts_wait_and_retry_feedback_from_readiness():
    orchestrator = ToolOrchestrator.__new__(ToolOrchestrator)

    feedback = orchestrator._extract_execution_feedback(
        raw_result={"success": True},
        data={
            "success": True,
            "readiness": "loading",
            "observed_after": {"title": "Steam", "status": "Loading"},
        },
        success=True,
    )

    assert feedback["action_status"] == "partial"
    assert feedback["recommended_action"] == "wait_and_retry"
    assert feedback["blocking_reason"] == "readiness:loading"
    assert feedback["world_state"]["readiness"] == "loading"


def test_execution_engine_retries_partial_success_before_completing(monkeypatch):
    class FakeTool:
        def get_capabilities(self):
            return {}

    class FakeRegistry:
        def __init__(self):
            self.tools = [FakeTool()]

    class FakeOrchestrator:
        def __init__(self):
            self.calls = 0

        def execute_tool_step(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return SimpleNamespace(
                    success=True,
                    data={"phase": "loading"},
                    error=None,
                    meta={
                        "execution_feedback": {
                            "action_status": "partial",
                            "recommended_action": "wait_and_retry",
                            "blocking_reason": "readiness:loading",
                            "wait_seconds": 0.0,
                        }
                    },
                )
            return SimpleNamespace(
                success=True,
                data={"phase": "ready"},
                error=None,
                meta={
                    "execution_feedback": {
                        "action_status": "success",
                        "recommended_action": "continue",
                    }
                },
            )

    step = TaskStep(
        step_id="step_1",
        description="Wait for readiness",
        tool_name="FakeTool",
        operation="do_work",
        parameters={},
        dependencies=[],
        expected_output="ready",
        max_retries=2,
    )
    state = ExecutionState(plan=ExecutionPlan(goal="demo", steps=[step], estimated_duration=1, complexity="simple"))
    engine = ExecutionEngine(tool_registry=FakeRegistry(), tool_orchestrator=FakeOrchestrator())
    monkeypatch.setattr(engine, "_get_feedback_wait_seconds", lambda feedback, skill_context: 0.0)

    result = engine._execute_step(step, state, skill_context=None)

    assert result.status == StepStatus.COMPLETED
    assert result.output == {"phase": "ready"}
    assert result.retry_count == 1
    assert result.meta["execution_feedback"]["action_status"] == "success"


def test_execution_supervisor_replans_on_completed_state_mismatch():
    supervisor = ExecutionSupervisor()
    step = TaskStep(
        step_id="step_1",
        description="Open app",
        tool_name="SystemControlTool",
        operation="launch_application",
        parameters={"name": "steam"},
        dependencies=[],
        expected_output="steam opened",
    )
    result = StepResult(
        step_id="step_1",
        status=StepStatus.COMPLETED,
        output={"window": "Steam"},
        meta={
            "execution_feedback": {
                "action_status": "partial",
                "recommended_action": "verify_state",
                "blocking_reason": "readiness:not_ready",
                "world_state": {"readiness": "not_ready"},
            }
        },
    )
    plan = ExecutionPlan(goal="demo", steps=[step], estimated_duration=1, complexity="simple")
    state = ExecutionState(plan=plan, step_results={"step_1": result})

    decision = supervisor.assess_wave(
        wave_results={"step_1": result},
        wave_steps=[step],
        remaining_steps=[],
        state=state,
        skill_context=None,
    )

    assert decision.action == DECISION_REPLAN
    assert decision.replan_context["advisory_steps"] == ["step_1"]


def test_execution_supervisor_prefers_bounded_local_retry_for_transient_advisory():
    supervisor = ExecutionSupervisor()
    step = TaskStep(
        step_id="step_1",
        description="Load page",
        tool_name="WebAccessTool",
        operation="fetch_page",
        parameters={"url": "https://example.com"},
        dependencies=[],
        expected_output="page content",
        retry_policy={"max_attempts": 2},
    )
    result = StepResult(
        step_id="step_1",
        status=StepStatus.COMPLETED,
        output={"status": "loading"},
        meta={
            "execution_feedback": {
                "action_status": "partial",
                "recommended_action": "wait_and_retry",
                "blocking_reason": "readiness:loading",
                "wait_seconds": 0.5,
            }
        },
    )
    state = ExecutionState(
        plan=ExecutionPlan(goal="demo", steps=[step], estimated_duration=1, complexity="simple"),
        step_results={"step_1": result},
    )

    decision = supervisor.assess_wave(
        wave_results={"step_1": result},
        wave_steps=[step],
        remaining_steps=[step],
        state=state,
        skill_context=None,
    )

    assert decision.action == DECISION_RETRY_STEP
    assert decision.retry_step_id == "step_1"
    assert decision.alt_tool is None
    assert decision.wait_seconds == 0.5


def test_execution_engine_inserts_local_recovery_retry_wave(monkeypatch):
    engine = ExecutionEngine(tool_registry=None)
    monkeypatch.setattr("application.use_cases.execution.execution_engine.time.sleep", lambda seconds: None)

    original = TaskStep(
        step_id="step_1",
        description="Load app state",
        tool_name="SystemControlTool",
        operation="focus_window",
        parameters={"title": "Steam"},
        dependencies=[],
        expected_output="focused",
        retry_policy={"max_attempts": 2},
    )
    plan = ExecutionPlan(goal="demo", steps=[original], estimated_duration=1, complexity="simple")
    state = ExecutionState(plan=plan, step_results={"step_1": StepResult(step_id="step_1", status=StepStatus.COMPLETED)})
    waves = [[original]]
    all_steps = [original]
    executed_step_ids = {"step_1"}
    decision = SupervisorDecision(
        action=DECISION_RETRY_STEP,
        reason="transient loading",
        retry_step_id="step_1",
        wait_seconds=1.0,
    )

    next_index = engine._apply_supervisor_decision(
        decision=decision,
        wave=[original],
        waves=waves,
        wave_index=0,
        remaining_after=[],
        all_steps=all_steps,
        executed_step_ids=executed_step_ids,
        state=state,
        plan=plan,
        pause_on_failure=False,
        skill_context=None,
    )

    assert next_index == 1
    assert len(waves) == 2
    assert waves[1][0].tool_name == "SystemControlTool"
    assert "local recovery retry" in waves[1][0].description
    assert state.recovery_attempts["step_1"] == 1
    assert "step_1" not in executed_step_ids


def test_execution_engine_records_step_state_in_registry(monkeypatch):
    class FakeTool:
        def get_capabilities(self):
            return {}

    class FakeRegistry:
        def __init__(self):
            self.tools = [FakeTool()]

    class FakeOrchestrator:
        def execute_tool_step(self, **kwargs):
            return SimpleNamespace(
                success=True,
                data={"text": "done"},
                error=None,
                meta={
                    "artifacts": [{"type": "file_ref", "path": "output/done.txt"}],
                    "execution_feedback": {
                        "action_status": "success",
                        "recommended_action": "continue",
                        "world_state": {"phase": "ready"},
                    },
                    "resolved_parameters": {"query": "x"},
                    "result_interpretation": {
                        "planner_signal": {"output_summary": "done summary"},
                    },
                },
            )

    step = TaskStep(
        step_id="step_1",
        description="Do work",
        tool_name="FakeTool",
        operation="run",
        parameters={"query": "x"},
        dependencies=[],
        expected_output="done",
    )
    state = ExecutionState(plan=ExecutionPlan(goal="demo", steps=[step], estimated_duration=1, complexity="simple"))
    engine = ExecutionEngine(tool_registry=FakeRegistry(), tool_orchestrator=FakeOrchestrator())
    monkeypatch.setattr(engine, "_get_feedback_wait_seconds", lambda feedback, skill_context: 0.0)

    result = engine._execute_step(step, state, skill_context=None)
    context = state.state_registry.build_planner_context()

    assert result.status == StepStatus.COMPLETED
    assert context["completed_summary"]["step_1"] == "done summary"
    assert context["completed_artifacts"]["step_1"]["kind"] == "structured"
    assert context["latest_world_state"]["phase"] == "ready"
