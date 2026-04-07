import json

from application.services.skill_context_hydrator import SkillContextHydrator
from application.services.skill_registry import SkillRegistry
from domain.entities.skill_models import SkillSelection
from infrastructure.services.llm_service import LLMService
from application.use_cases.execution.result_interpreter import ResultInterpreter
from tools.computer_use.input_automation_tool import InputAutomationTool


def test_computer_automation_skill_exposes_planner_native_hints():
    registry = SkillRegistry()
    registry.load_all()

    skill = registry.get("computer_automation")
    assert skill is not None
    assert "ComputerUseController" not in skill.preferred_tools
    assert skill.metadata["vision_mode"] is True
    assert skill.metadata["screenshot_at_each_step"] is True

    selection = SkillSelection(
        matched=True,
        skill_name="computer_automation",
        category="computer",
        confidence=1.0,
    )
    context = SkillContextHydrator.build_context(selection, skill, "open steam and list my games")

    assert context.planning_hints["observe_act_verify_loop"] is True
    assert context.planning_hints["failure_categories"] == [
        "TIMING_ISSUE",
        "ENVIRONMENT_CHANGED",
        "NO_EFFECT",
    ]
    assert context.validation_rules["skill_constraints"]


def test_llm_service_routes_image_calls_to_dedicated_vision_path():
    class FakeClient:
        def __init__(self):
            self.calls = []

        def vision(self, prompt, **kwargs):
            self.calls.append(("vision", prompt, kwargs))
            return json.dumps({"items": ["Library"]})

        def _call_llm(self, prompt, **kwargs):
            self.calls.append(("text", prompt, kwargs))
            return "plain-response"

        def _extract_json(self, response):
            return json.loads(response)

    client = FakeClient()
    service = LLMService(client)

    text = service.generate("Describe the screenshot", image_path="output/screen.png")
    structured = service.generate_structured(
        "Return JSON only",
        image_path="output/screen.png",
        container="object",
    )

    assert text == json.dumps({"items": ["Library"]})
    assert structured == {"items": ["Library"]}
    assert client.calls[0][0] == "vision"
    assert client.calls[1][0] == "vision"
    assert all(call[0] == "vision" for call in client.calls[:2])


def test_desktop_tool_errors_surface_failure_category_to_runtime_feedback():
    tool = InputAutomationTool()
    error = tool._error_response("TIMEOUT", "UI still loading", recoverable=True)

    interpretation = ResultInterpreter().interpret(
        raw_result=error,
        data=error,
        success=False,
        error=error["message"],
        tool_name="InputAutomationTool",
        operation="smart_click",
    )

    assert error["failure_category"] == "TIMING_ISSUE"
    assert interpretation.execution_feedback["failure_category"] == "TIMING_ISSUE"
    assert interpretation.planner_signal["failure_category"] == "TIMING_ISSUE"
