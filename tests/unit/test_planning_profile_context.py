from unittest.mock import Mock

from api.chat.skill_handler import build_planner_context
from application.planning.create_plan import CreatePlanUseCase
from domain.entities.skill_models import SkillDefinition
from domain.entities.task import ExecutionPlan, TaskStep
from infrastructure.llm.prompt_builder import PlanningPromptBuilder


class _SkillRegistryStub:
    def __init__(self, skills):
        self._skills = skills

    def get(self, name):
        return self._skills.get(name)


def _computer_skill() -> SkillDefinition:
    return SkillDefinition(
        name="computer_automation",
        category="computer",
        description="Desktop automation and local operations.",
        trigger_examples=["open steam", "list files"],
        preferred_tools=[
            "FilesystemTool",
            "ShellTool",
            "SystemControlTool",
            "InputAutomationTool",
            "ScreenPerceptionTool",
            "BenchmarkRunnerTool",
        ],
        required_tools=[],
        preferred_connectors=[],
        input_types=["path", "command"],
        output_types=["text"],
        verification_mode="side_effect_observed",
        risk_level="high",
        ui_renderer="automation_result",
        fallback_strategy="safe_direct_tool_routing",
        skill_dir="skills/computer_automation",
        instructions_path="skills/computer_automation/SKILL.md",
        metadata={
            "vision_mode": True,
            "screenshot_at_each_step": True,
            "observe_act_verify_loop": True,
            "skill_constraints": [
                "Use direct desktop tools for simple UI tasks",
            ],
            "workflow_guidance": [
                "Focus the app before interacting.",
            ],
            "failure_categories": ["TIMING_ISSUE", "NO_EFFECT"],
        },
    )


def test_build_planner_context_narrows_desktop_detail_lookup_tools():
    skill_reg = _SkillRegistryStub({"computer_automation": _computer_skill()})
    selection = {
        "matched": True,
        "skill_name": "computer_automation",
        "category": "computer",
        "confidence": 0.95,
    }

    context = build_planner_context(
        selection,
        skill_reg,
        user_request="open steam and find how many hours i have played conquerors blade",
        domain_hint="computer",
    )

    skill_context = context["skill_context"]
    assert context["planning_profile"] == "desktop_ui_detail_lookup"
    assert skill_context["planning_profile"] == "desktop_ui_detail_lookup"
    assert skill_context["preferred_tools"] == [
        "SystemControlTool",
        "InputAutomationTool",
        "ScreenPerceptionTool",
    ]
    assert skill_context["include_past_plans"] is False
    assert skill_context["include_memory_context"] is False
    assert skill_context["use_compact_schema"] is True


def test_build_planner_context_narrows_filesystem_profile_tools():
    skill_reg = _SkillRegistryStub({"computer_automation": _computer_skill()})
    selection = {
        "matched": True,
        "skill_name": "computer_automation",
        "category": "computer",
        "confidence": 0.95,
    }

    context = build_planner_context(
        selection,
        skill_reg,
        user_request="read this json file and write the result to another file",
        domain_hint="computer",
    )

    skill_context = context["skill_context"]
    assert context["planning_profile"] == "filesystem_local"
    assert skill_context["preferred_tools"] == [
        "FilesystemTool",
        "ShellTool",
    ]
    assert skill_context["include_memory_context"] is True
    assert skill_context["use_compact_schema"] is False


def test_compact_desktop_prompt_omits_heavy_sections_and_irrelevant_tools():
    builder = PlanningPromptBuilder()
    prompt = builder.build_planning_prompt(
        goal="open steam and find how many hours i have played conquerors blade",
        tools={
            "BenchmarkRunnerTool": [{"name": "run", "parameters": [], "description": "bench"}],
            "FilesystemTool": [{"name": "read_file", "parameters": [], "description": "read"}],
            "SystemControlTool": [{"name": "launch_application", "parameters": [{"name": "name", "required": True}], "description": "launch"}],
            "InputAutomationTool": [{"name": "smart_click", "parameters": [{"name": "target", "required": True}], "description": "click"}],
            "ScreenPerceptionTool": [{"name": "extract_text", "parameters": [{"name": "prompt", "required": False}], "description": "extract"}],
        },
        skill_context={
            "skill_name": "computer_automation",
            "category": "computer",
            "planning_profile": "desktop_ui_detail_lookup",
            "preferred_tools": ["SystemControlTool", "InputAutomationTool", "ScreenPerceptionTool"],
            "domain_hint": "computer",
            "include_past_plans": False,
            "include_memory_context": False,
            "include_previous_context": False,
            "include_adaptive_rules": False,
            "use_compact_schema": True,
            "profile_guidance": ["Prefer labeled detail extraction."],
        },
        past_plans=[],
        unified_context="memory that should not be included",
    )

    assert "BenchmarkRunnerTool" not in prompt
    assert "FilesystemTool" not in prompt
    assert "PAST APPROACHES (reference only)" not in prompt
    assert "MEMORY:" not in prompt
    assert "Planning profile: desktop_ui_detail_lookup" in prompt
    assert "Optional step fields:" in prompt
    assert '"checkpoint_policy": "on_failure"' not in prompt


def test_create_plan_skips_memory_and_past_plan_fetch_for_compact_desktop_profile():
    llm_gateway = Mock()
    llm_gateway.generate_plan.return_value = '{"goal":"x","complexity":"simple","estimated_duration":5,"requires_approval":false,"steps":[]}'

    tool_repo = Mock()
    tool_repo.get_capabilities.return_value = {}

    memory_repo = Mock()
    prompt_builder = Mock()
    prompt_builder.build_planning_prompt.return_value = "prompt"

    validator = Mock()
    validator.parse_llm_response.return_value = {
        "goal": "x",
        "complexity": "simple",
        "estimated_duration": 5,
        "requires_approval": False,
        "steps": [],
    }
    validator.validate.return_value = ExecutionPlan(
        goal="x",
        complexity="simple",
        estimated_duration=5,
        requires_approval=False,
        steps=[
            TaskStep(
                step_id="step_1",
                description="Launch Steam",
                tool_name="SystemControlTool",
                operation="launch_application",
                parameters={"name": "steam"},
                dependencies=[],
                expected_output="Steam opens",
                domain="computer",
            ),
            TaskStep(
                step_id="step_2",
                description="Extract the requested detail",
                tool_name="ScreenPerceptionTool",
                operation="extract_text",
                parameters={"prompt": "Find the game and extract playtime", "target_app": "steam"},
                dependencies=["step_1"],
                expected_output="Requested Steam detail is extracted",
                domain="computer",
            ),
        ],
    )

    use_case = CreatePlanUseCase(llm_gateway, tool_repo, memory_repo, prompt_builder, validator)
    plan = use_case.execute(
        "open steam and find how many hours i have played conquerors blade",
        context={
            "skill_context": {
                "skill_name": "computer_automation",
                "preferred_tools": ["SystemControlTool", "InputAutomationTool", "ScreenPerceptionTool"],
                "include_past_plans": False,
                "include_memory_context": False,
            }
        },
    )

    assert isinstance(plan, ExecutionPlan)
    memory_repo.find_similar_plans.assert_not_called()
    memory_repo.search_context.assert_not_called()


def test_detail_lookup_prompt_guidance_prefers_goal_focused_extraction():
    builder = PlanningPromptBuilder()

    prompt = builder.build_planning_prompt(
        goal="open the app and find the current order status for item 1042",
        tools={
            "SystemControlTool": [{"name": "launch_application", "parameters": [{"name": "name", "required": True}], "description": "launch"}],
            "InputAutomationTool": [{"name": "smart_click", "parameters": [{"name": "target", "required": True}], "description": "click"}],
            "ScreenPerceptionTool": [{"name": "extract_text", "parameters": [{"name": "prompt", "required": False}], "description": "extract"}],
        },
        skill_context={
            "skill_name": "computer_automation",
            "category": "computer",
            "planning_profile": "desktop_ui_detail_lookup",
            "preferred_tools": ["SystemControlTool", "InputAutomationTool", "ScreenPerceptionTool"],
            "include_past_plans": False,
            "include_memory_context": False,
            "include_previous_context": False,
            "include_adaptive_rules": False,
            "use_compact_schema": True,
        },
        past_plans=[],
        unified_context="",
    )

    assert "named-item detail lookup" in prompt
    assert "Do not plan a broad scan of all visible items" in prompt


def test_goal_focused_extraction_prompt_is_generic_not_app_specific():
    use_case = CreatePlanUseCase.__new__(CreatePlanUseCase)

    prompt = use_case._build_goal_focused_extraction_prompt(
        "find the order total for invoice 1042 in the desktop app"
    )

    assert "Extract only the specific detail needed to answer this request" in prompt
    assert "invoice 1042" in prompt
    assert "Do not return unrelated visible items" in prompt


def test_goal_focused_extraction_prompt_carries_named_target_and_field_hints():
    use_case = CreatePlanUseCase.__new__(CreatePlanUseCase)

    prompt = use_case._build_goal_focused_extraction_prompt(
        "can u open steam and find out how many hours of game i have in conquerors balde..games are lsited in library"
    )

    assert 'Named target item: "conquerors balde"' in prompt
    assert "Requested field hint: playtime in hours" in prompt


def test_deep_planning_prompt_adds_decomposition_guidance():
    builder = PlanningPromptBuilder()

    prompt = builder.build_planning_prompt(
        goal="audit the repository and produce a safe rollout plan",
        tools={
            "GlobTool": [{"name": "glob", "parameters": [{"name": "pattern", "required": True}], "description": "find files"}],
            "FilesystemTool": [{"name": "read_file", "parameters": [{"name": "path", "required": True}], "description": "read file"}],
        },
        skill_context={
            "skill_name": "code_workspace",
            "category": "development",
            "planning_mode": "deep",
            "preferred_tools": ["GlobTool", "FilesystemTool"],
            "include_past_plans": True,
            "include_memory_context": True,
            "include_previous_context": True,
            "include_adaptive_rules": True,
            "use_compact_schema": False,
        },
        past_plans=[],
        unified_context="recent repo refactor context",
    )

    assert "DEEP PLANNING MODE:" in prompt
    assert "Surface assumptions" in prompt
