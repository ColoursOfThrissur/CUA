import asyncio
from types import SimpleNamespace

from application.evolution.context_builder import ContextBuilder
from application.evolution.evolution_processor import EvolutionProcessor
from application.use_cases.evolution.evolution_queue import QueuedEvolution
from application.use_cases.evolution.tool_proposal_generator import EvolutionProposalGenerator


class _DummyLogger:
    def info(self, *args, **kwargs):
        return None

    def debug(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def error(self, *args, **kwargs):
        return None


class _FakeLLM:
    def _call_llm(self, prompt, temperature=0.2, max_tokens=None, expect_json=True):
        return """
        {
          "action_type": "add_capability",
          "description": "Add real-time MCP server health monitoring",
          "target_functions": [],
          "changes": ["Add monitoring capability", "Persist health snapshots"],
          "implementation_sketch": {},
          "expected_improvement": "Server health can be monitored continuously",
          "confidence": 0.84,
          "risk_level": 0.22,
          "justification": "Needed to expose server availability and performance"
        }
        """


def _install_fake_skill_registry(monkeypatch):
    import application.services.skill_registry as skill_registry_module

    skill = SimpleNamespace(
        name="system_health",
        category="monitoring",
        verification_mode="output_validation",
        ui_renderer="status_panel",
        output_types=["health_status"],
        preferred_tools=["SystemHealthTool"],
        required_tools=[],
        risk_level="low",
        fallback_strategy="degrade_gracefully",
    )

    def fake_load_all(self):
        return None

    def fake_list_all(self):
        return [skill]

    def fake_get(self, name):
        return skill if name == skill.name else None

    monkeypatch.setattr(skill_registry_module.SkillRegistry, "load_all", fake_load_all)
    monkeypatch.setattr(skill_registry_module.SkillRegistry, "list_all", fake_list_all)
    monkeypatch.setattr(skill_registry_module.SkillRegistry, "get", fake_get)


def test_proposal_generator_uses_skill_contract_helper_without_signature_error(monkeypatch):
    _install_fake_skill_registry(monkeypatch)

    generator = EvolutionProposalGenerator(_FakeLLM())
    analysis = {
        "tool_name": "SystemHealthTool",
        "health_score": 95.0,
        "code_quality_category": "HEALTHY",
        "success_rate": 0.98,
        "user_prompt": "Add a capability to monitor and log server health status in real-time.",
        "current_code": "class SystemHealthTool:\n    pass\n",
        "llm_issues": [],
        "llm_improvements": [],
    }

    proposal = generator.generate_proposal(analysis)

    assert proposal is not None
    assert proposal["tool_spec"]["target_skill"] == "system_health"
    assert proposal["tool_spec"]["target_category"] == "monitoring"
    assert proposal["tool_spec"]["artifact_types"] == ["health_status"]


def test_context_builder_uses_skill_inference_contract(monkeypatch):
    _install_fake_skill_registry(monkeypatch)

    builder = ContextBuilder(_DummyLogger())
    evolution = QueuedEvolution(
        tool_name="SystemHealthTool",
        urgency_score=0.5,
        impact_score=0.7,
        feasibility_score=0.8,
        timing_score=0.6,
        reason="Improve monitoring",
        metadata={"is_enhancement": True},
    )

    context = builder.build_context("SystemHealthTool", evolution)

    assert context is not None
    assert context.skill_name == "system_health"
    assert context.category == "monitoring"
    assert context.verification_mode == "output_validation"
    assert context.preferred_tools == ["SystemHealthTool"]


def test_evolution_processor_builds_execution_context_from_skill_contract(monkeypatch):
    _install_fake_skill_registry(monkeypatch)

    processor = EvolutionProcessor(
        logger=_DummyLogger(),
        queue=SimpleNamespace(),
        config={"learning_enabled": False, "auto_approve_threshold": 90},
        llm_client=None,
        test_orchestrator=None,
        evolution_flow=None,
        quality_analyzer=None,
    )
    evolution = QueuedEvolution(
        tool_name="SystemHealthTool",
        urgency_score=0.5,
        impact_score=0.7,
        feasibility_score=0.8,
        timing_score=0.6,
        reason="Improve monitoring",
        metadata={"is_enhancement": True},
    )

    context = processor._build_execution_context_for_auto_evolution("SystemHealthTool", evolution)

    assert context is not None
    assert context.skill_name == "system_health"
    assert context.category == "monitoring"
    assert context.verification_mode == "output_validation"


def test_evolution_processor_create_tool_branch_runs_without_skill_contract_lookup(monkeypatch):
    class FakeQueue:
        def __init__(self):
            self.in_progress = None
            self.failed = {}
            self.completed = []

        def mark_in_progress(self, tool_name):
            self.in_progress = tool_name

        def mark_failed(self, tool_name, error):
            self.failed[tool_name] = error

        def mark_completed(self, tool_name):
            self.completed.append(tool_name)
            self.in_progress = None

    class FakeCreationFlow:
        def __init__(self):
            self.last_spec = {"name": "MCPServerHealthTool"}

        def create_tool(self, gap_description, llm_client, preferred_name):
            return {"success": True, "message": "created"}

    class FakeTestOrchestrator:
        def run_test_suite(self, tool_name):
            return {"overall_score": 0}

    queue = FakeQueue()
    processor = EvolutionProcessor(
        logger=_DummyLogger(),
        queue=queue,
        config={"learning_enabled": False, "auto_approve_threshold": 90},
        llm_client=object(),
        test_orchestrator=FakeTestOrchestrator(),
        evolution_flow=None,
        quality_analyzer=None,
    )
    processor.tool_creation_flow = FakeCreationFlow()

    evolution = QueuedEvolution(
        tool_name="CREATE::mcp_server_health",
        urgency_score=0.5,
        impact_score=0.7,
        feasibility_score=0.8,
        timing_score=0.6,
        reason="Create MCP server health monitoring tool",
        metadata={"kind": "create_tool", "preferred_name": "MCPServerHealthTool"},
    )

    asyncio.run(processor._process_evolution(evolution))

    assert not queue.failed
    assert "CREATE::mcp_server_health" in queue.completed
