import json

from core.skills import SkillLoader, SkillRegistry, SkillSelector, build_domain_catalog, build_skill_planning_context
from core.task_planner import TaskPlanner
from core.tool_creation.spec_generator import SpecGenerator


class _FakeLLM:
    def __init__(self):
        self.last_prompt = None

    def _call_llm(self, prompt, temperature=0.0, max_tokens=None, expect_json=False):
        self.last_prompt = prompt
        return json.dumps(
            {
                "goal": "test goal",
                "complexity": "simple",
                "estimated_duration": 5,
                "requires_approval": False,
                "steps": [
                    {
                        "step_id": "step_1",
                        "description": "List files",
                        "tool_name": "FilesystemTool",
                        "operation": "list_directory",
                        "parameters": {"path": "."},
                        "dependencies": [],
                        "expected_output": "Directory listing",
                        "retry_on_failure": True,
                    }
                ],
            }
        )

    def _extract_json(self, response):
        return json.loads(response)


class _FakeSpecLLM:
    def __init__(self):
        self.last_prompt = None

    def _call_llm(self, prompt, temperature=0.0, max_tokens=None, expect_json=False):
        self.last_prompt = prompt
        return json.dumps(
            {
                "name": "WebsiteFactsTool",
                "domain": "web",
                "inputs": [
                    {
                        "operation": "extract_facts",
                        "parameters": [
                            {"name": "url", "type": "string", "description": "URL", "required": True}
                        ],
                    }
                ],
                "outputs": ["structured_extraction"],
                "dependencies": ["self.services.http", "self.services.storage"],
                "risk_level": 0.4,
            }
        )

    def _extract_json(self, response):
        return json.loads(response)


class _FakeParamType:
    value = "string"


class _FakeParam:
    def __init__(self, name, required=False):
        self.name = name
        self.required = required
        self.description = name
        self.type = _FakeParamType()


class _FakeCapability:
    def __init__(self, description, parameters):
        self.description = description
        self.parameters = parameters


class FilesystemTool:
    def get_capabilities(self):
        return {
            "list_directory": _FakeCapability(
                "List a directory",
                [_FakeParam("path", required=False)],
            )
        }


class _FakeRegistryForPlanner:
    @property
    def tools(self):
        return [FilesystemTool()]


def test_skill_loader_loads_repo_skills():
    loader = SkillLoader()

    skills = loader.load_all()

    assert "web_research" in skills
    assert "computer_automation" in skills
    assert "code_workspace" in skills


def test_skill_selector_routes_web_request():
    registry = SkillRegistry()
    registry.load_all()
    selector = SkillSelector()

    selection = selector.select_skill("Research this topic on the web and compare sources", registry)

    assert selection.matched is True
    assert selection.skill_name == "web_research"
    assert selection.category == "web"


def test_skill_selector_routes_code_request():
    registry = SkillRegistry()
    registry.load_all()
    selector = SkillSelector()

    selection = selector.select_skill("Inspect this codebase and fix this bug", registry)

    assert selection.matched is True
    assert selection.skill_name == "code_workspace"
    assert selection.category == "development"


def test_build_skill_planning_context():
    registry = SkillRegistry()
    registry.load_all()
    skill = registry.get("computer_automation")

    planning_context = build_skill_planning_context(skill)

    assert planning_context.skill_name == "computer_automation"
    assert "FilesystemTool" in planning_context.preferred_tools
    assert planning_context.category == "computer"


def test_build_domain_catalog_groups_tools_by_skill_domain():
    registry = SkillRegistry()
    registry.load_all()

    class _ToolRegistry:
        @property
        def tools(self):
            return [FilesystemTool()]

    catalog = build_domain_catalog(registry, _ToolRegistry(), selected_skill_name="computer_automation")

    assert catalog["selected_skill"] == "computer_automation"
    computer_domain = next(domain for domain in catalog["domains"] if domain["name"] == "computer")
    assert computer_domain["selected"] is True
    assert computer_domain["tools"][0]["name"] == "FilesystemTool"


def test_task_planner_includes_skill_guidance():
    llm = _FakeLLM()
    planner = TaskPlanner(llm, _FakeRegistryForPlanner())

    plan = planner.plan_task(
        "List files",
        context={
            "skill_context": {
                "skill_name": "computer_automation",
                "category": "computer",
                "instructions_summary": "Use local file and shell tools.",
                "preferred_tools": ["FilesystemTool", "ShellTool"],
                "required_tools": [],
                "verification_mode": "side_effect_observed",
                "output_types": ["directory_listing"],
                "ui_renderer": "automation_result",
                "skill_constraints": ["Preferred tools: FilesystemTool, ShellTool"],
            }
        },
    )

    assert plan.goal == "test goal"
    assert "Selected skill: computer_automation" in llm.last_prompt
    assert "Expected outputs: directory_listing" in llm.last_prompt


def test_spec_generator_honors_skill_context():
    llm = _FakeSpecLLM()
    generator = SpecGenerator(capability_graph=None)

    spec = generator.propose_tool_spec(
        "Create a tool that extracts structured findings from websites",
        llm,
        preferred_tool_name="WebsiteFactsTool",
        skill_context={"target_skill": "web_research", "target_category": "web"},
    )

    assert spec is not None
    assert spec["name"] == "WebsiteFactsTool"
    assert spec["target_skill"] == "web_research"
    assert spec["target_category"] == "web"
    assert spec["artifact_types"] == ["structured_extraction"]
    assert "Target skill: web_research" in llm.last_prompt


def test_spec_generator_enriches_architecture_contract_from_skill_context():
    llm = _FakeSpecLLM()
    generator = SpecGenerator(capability_graph=None)

    spec = generator.propose_tool_spec(
        "Create a tool that extracts structured findings from websites",
        llm,
        preferred_tool_name="WebsiteFactsTool",
        skill_context={
            "target_skill": "web_research",
            "target_category": "web",
            "verification_mode": "source_backed",
            "ui_renderer": "research_summary",
            "output_types": ["structured_extraction", "source_comparison"],
        },
    )

    assert spec is not None
    assert spec["verification_mode"] == "source_backed"
    assert spec["ui_renderer"] == "research_summary"
    assert spec["artifact_types"] == ["structured_extraction"]
