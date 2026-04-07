from types import SimpleNamespace

from api.chat.tool_executor import select_primary_result
from application.use_cases.execution.execution_engine import ExecutionEngine, StepStatus
from domain.entities.task import ExecutionPlan, TaskStep


class SystemControlTool:
    def get_capabilities(self):
        return {}


class ScreenPerceptionTool:
    def get_capabilities(self):
        return {}


class InputAutomationTool:
    def get_capabilities(self):
        return {}


class FakeRegistry:
    def __init__(self):
        self.tools = [
            SystemControlTool(),
            ScreenPerceptionTool(),
            InputAutomationTool(),
        ]


class SequencedOrchestrator:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def execute_tool_step(self, **kwargs):
        tool_name = kwargs.get("tool_name")
        operation = kwargs.get("operation")
        self.calls.append((tool_name, operation))
        try:
            payload = self.responses.pop(0)
        except IndexError as exc:
            raise AssertionError(f"Unexpected tool call: {tool_name}.{operation}") from exc
        return SimpleNamespace(
            success=payload.get("success", True),
            data=payload.get("data"),
            error=payload.get("error"),
            meta=payload.get("meta", {"execution_feedback": {"action_status": "success", "recommended_action": "continue"}}),
        )


def test_execution_engine_short_circuits_desktop_detail_lookup_after_answer_ready():
    plan = ExecutionPlan(
        goal="open steam and find how many hours i have played conquerors blade",
        steps=[
            TaskStep(
                step_id="step_1",
                description="Open Steam",
                tool_name="SystemControlTool",
                operation="launch_application",
                parameters={"name": "steam"},
                dependencies=[],
                expected_output="Steam opens",
            ),
            TaskStep(
                step_id="step_2",
                description="Extract requested detail",
                tool_name="ScreenPerceptionTool",
                operation="extract_text",
                parameters={"prompt": "Extract the requested detail", "target_app": "steam"},
                dependencies=["step_1"],
                expected_output="Target detail extracted",
            ),
            TaskStep(
                step_id="step_3",
                description="Redundant follow-up",
                tool_name="InputAutomationTool",
                operation="press_key",
                parameters={"key": "down"},
                dependencies=["step_2"],
                expected_output="Moved selection",
            ),
        ],
        estimated_duration=5,
        complexity="simple",
    )
    orchestrator = SequencedOrchestrator([
        {"data": {"pid": 1, "name": "steam"}},
        {
            "data": {
                "success": True,
                "target": "Conqueror's Blade",
                "requested_field": "playtime_hours",
                "field_value": "21.2",
                "answer_ready": True,
                "ambiguous": False,
                "active_window_title": "Steam",
                "summary": "Conqueror's Blade shows 21.2 hours.",
            }
        },
    ])
    engine = ExecutionEngine(tool_registry=FakeRegistry(), tool_orchestrator=orchestrator)

    state = engine.execute_plan(
        plan,
        execution_id="desktop_policy_short_circuit",
        skill_context={"skill_name": "computer_automation", "planning_profile": "desktop_ui_detail_lookup"},
    )

    assert orchestrator.calls == [
        ("SystemControlTool", "launch_application"),
        ("ScreenPerceptionTool", "extract_text"),
    ]
    assert state.status == "completed"
    assert state.step_results["step_1"].status == StepStatus.COMPLETED
    assert state.step_results["step_2"].status == StepStatus.COMPLETED
    assert state.step_results["step_3"].status == StepStatus.SKIPPED


def test_execution_engine_inserts_local_desktop_recovery_when_target_app_drifts():
    plan = ExecutionPlan(
        goal="open steam and read the visible library details",
        steps=[
            TaskStep(
                step_id="step_1",
                description="Open Steam",
                tool_name="SystemControlTool",
                operation="launch_application",
                parameters={"name": "steam"},
                dependencies=[],
                expected_output="Steam opens",
            ),
            TaskStep(
                step_id="step_2",
                description="Read current state",
                tool_name="ScreenPerceptionTool",
                operation="extract_text",
                parameters={"prompt": "Read the needed visible text", "target_app": "steam"},
                dependencies=["step_1"],
                expected_output="Visible text extracted",
            ),
            TaskStep(
                step_id="step_3",
                description="Retry extraction",
                tool_name="ScreenPerceptionTool",
                operation="extract_text",
                parameters={"prompt": "Read the needed visible text", "target_app": "steam"},
                dependencies=["step_2"],
                expected_output="Visible text extracted",
            ),
        ],
        estimated_duration=5,
        complexity="simple",
    )
    orchestrator = SequencedOrchestrator([
        {"data": {"pid": 1, "name": "steam"}},
        {
            "data": {
                "success": True,
                "items": [],
                "summary": "",
                "active_window_title": "Visual Studio Code",
            }
        },
        {
            "data": {
                "success": True,
                "visual_state": {
                    "target_app_visible": True,
                    "target_app_active": True,
                    "current_view": "library",
                    "visible_targets": ["Conqueror's Blade"],
                }
            }
        },
        {
            "data": {
                "success": True,
                "items": ["Conqueror's Blade"],
                "summary": "Visible item: Conqueror's Blade.",
                "active_window_title": "Steam",
            }
        },
    ])
    engine = ExecutionEngine(tool_registry=FakeRegistry(), tool_orchestrator=orchestrator)

    state = engine.execute_plan(
        plan,
        execution_id="desktop_policy_recovery",
        skill_context={"skill_name": "computer_automation", "planning_profile": "desktop_ui_extraction"},
    )

    assert ("ScreenPerceptionTool", "infer_visual_state") in orchestrator.calls
    recovery_ids = [step_id for step_id in state.step_results if step_id.startswith("desktop_policy_recovery_")]
    assert recovery_ids
    assert state.step_results["step_3"].status == StepStatus.COMPLETED


def test_execution_engine_does_not_short_circuit_extraction_when_items_come_from_wrong_app():
    plan = ExecutionPlan(
        goal="open steam and list the visible library games",
        steps=[
            TaskStep(
                step_id="step_1",
                description="Open Steam",
                tool_name="SystemControlTool",
                operation="launch_application",
                parameters={"name": "steam"},
                dependencies=[],
                expected_output="Steam opens",
            ),
            TaskStep(
                step_id="step_2",
                description="Extract games",
                tool_name="ScreenPerceptionTool",
                operation="extract_text",
                parameters={"prompt": "Extract all visible game titles from the Steam library view", "target_app": "steam"},
                dependencies=["step_1"],
                expected_output="Visible library titles extracted",
            ),
            TaskStep(
                step_id="step_3",
                description="Retry extraction",
                tool_name="ScreenPerceptionTool",
                operation="extract_text",
                parameters={"prompt": "Extract all visible game titles from the Steam library view", "target_app": "steam"},
                dependencies=["step_2"],
                expected_output="Visible library titles extracted",
            ),
        ],
        estimated_duration=5,
        complexity="simple",
    )
    orchestrator = SequencedOrchestrator([
        {"data": {"pid": 1, "name": "steam"}},
        {
            "data": {
                "success": True,
                "items": ["Repo", "Remote", "Tunnels"],
                "summary": "Visible items detected.",
                "active_window_title": "Visual Studio Code",
            }
        },
        {
            "data": {
                "success": True,
                "items": ["Apex Legends", "Dota 2"],
                "summary": "Visible items: Apex Legends, Dota 2.",
                "active_window_title": "Steam",
            }
        },
    ])
    engine = ExecutionEngine(tool_registry=FakeRegistry(), tool_orchestrator=orchestrator)

    state = engine.execute_plan(
        plan,
        execution_id="desktop_policy_wrong_window_guard",
        skill_context={"skill_name": "computer_automation", "planning_profile": "desktop_ui_extraction"},
    )

    assert orchestrator.calls[0:2] == [
        ("SystemControlTool", "launch_application"),
        ("ScreenPerceptionTool", "extract_text"),
    ]
    assert ("ScreenPerceptionTool", "infer_visual_state") in orchestrator.calls
    assert state.status == "completed"
    assert state.step_results["step_2"].status == StepStatus.COMPLETED
    assert state.step_results["step_3"].status in {StepStatus.COMPLETED, StepStatus.SKIPPED}


def test_select_primary_result_prefers_answer_quality_over_payload_length():
    results = [
        {
            "tool": "ScreenPerceptionTool",
            "operation": "extract_text",
            "data": {
                "success": True,
                "target": "Conqueror's Blade",
                "requested_field": "playtime_hours",
                "field_value": "21.2",
                "answer_ready": True,
                "summary": "Conqueror's Blade shows 21.2 hours.",
            },
        },
        {
            "tool": "ScreenPerceptionTool",
            "operation": "extract_text",
            "data": {
                "success": True,
                "items": ["noise"] * 200,
                "summary": "",
                "ambiguous": True,
            },
        },
    ]
    executed_history = [
        {"tool": "ScreenPerceptionTool", "operation": "extract_text"},
        {"tool": "ScreenPerceptionTool", "operation": "extract_text"},
    ]

    primary, tool_name, operation = select_primary_result(results, executed_history)

    assert tool_name == "ScreenPerceptionTool"
    assert operation == "extract_text"
    assert primary["answer_ready"] is True
    assert primary["field_value"] == "21.2"


def test_select_primary_result_prefers_grounded_desktop_result_over_wrong_window_noise():
    results = [
        {
            "tool": "ScreenPerceptionTool",
            "operation": "extract_text",
            "data": {
                "success": True,
                "items": ["Repo", "Remote", "Tunnels", "Ports", "Explorer"],
                "summary": "Visible items detected.",
                "grounded": False,
                "grounding": {"target_app": "steam", "blocking_reason": "target_app_not_confirmed:steam"},
                "active_window_title": "Visual Studio Code",
            },
        },
        {
            "tool": "ScreenPerceptionTool",
            "operation": "extract_text",
            "data": {
                "success": True,
                "items": ["Apex Legends", "Dota 2"],
                "summary": "Visible library entries include Apex Legends and Dota 2.",
                "grounded": True,
                "grounding": {"target_app": "steam"},
                "active_window_title": "Steam",
            },
        },
    ]
    executed_history = [
        {"tool": "ScreenPerceptionTool", "operation": "extract_text"},
        {"tool": "ScreenPerceptionTool", "operation": "extract_text"},
    ]

    primary, tool_name, operation = select_primary_result(results, executed_history)

    assert tool_name == "ScreenPerceptionTool"
    assert operation == "extract_text"
    assert primary["grounded"] is True
    assert primary["items"] == ["Apex Legends", "Dota 2"]
