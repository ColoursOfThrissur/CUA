from core.architecture_contract import derive_skill_contract_for_tool
from core.tool_evolution.proposal_generator import EvolutionProposalGenerator
from core.tool_evolution.validator import EvolutionValidator


class _FakeLLM:
    def _call_llm(self, prompt, temperature=0.0, max_tokens=None, expect_json=False):
        return """{
  "action_type": "improve_logic",
  "description": "Improve source handling for web research responses",
  "changes": ["Tighten result extraction", "Preserve source-backed outputs"],
  "expected_improvement": "More reliable web result handling",
  "confidence": 0.8,
  "risk_level": 0.3,
  "justification": "Web research tools should keep source-backed output quality"
}"""


def _tool_code(class_name: str) -> str:
    return f"""from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel
from tools.tool_result import ToolResult

class {class_name}(BaseTool):
    def __init__(self, orchestrator=None):
        self.description = "desc"
        self.services = orchestrator.get_services(self.__class__.__name__) if orchestrator else None
        super().__init__()

    def register_capabilities(self):
        cap = ToolCapability(
            name="search_web",
            description="search",
            parameters=[Parameter(name="query", type=ParameterType.STRING, description="query", required=True)],
            returns="payload",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(cap, self._search_web)

    def _search_web(self, **kwargs):
        return {{"success": True, "query": kwargs.get("query")}}

    def execute(self, operation: str, **kwargs) -> ToolResult:
        return self.execute_capability(operation, **kwargs)
"""


def test_derive_skill_contract_for_existing_tool():
    contract = derive_skill_contract_for_tool("WebAccessTool")

    assert contract["target_skill"] == "web_research"
    assert contract["target_category"] == "web"
    assert contract["verification_mode"] == "source_backed"
    assert contract["ui_renderer"] == "research_summary"
    assert "research_summary" in contract["output_types"]


def test_evolution_proposal_generator_attaches_tool_spec():
    generator = EvolutionProposalGenerator(_FakeLLM())
    proposal = generator.generate_proposal(
        {
            "tool_name": "WebAccessTool",
            "health_score": 85.0,
            "code_quality_category": "HEALTHY_WITH_MINOR_ISSUES",
            "success_rate": 0.9,
            "current_code": _tool_code("WebAccessTool"),
            "llm_issues": [],
            "llm_improvements": [],
            "issues": [],
        }
    )

    assert proposal is not None
    assert proposal["tool_spec"]["target_skill"] == "web_research"
    assert proposal["tool_spec"]["verification_mode"] == "source_backed"
    assert proposal["tool_spec"]["ui_renderer"] == "research_summary"
    assert proposal["tool_spec"]["artifact_types"]


def test_evolution_validator_rejects_broken_architecture_contract():
    validator = EvolutionValidator()
    code = _tool_code("WebAccessTool")
    ok, error = validator.validate(
        original_code=code,
        improved_code=code,
        proposal={
            "tool_spec": {
                "name": "WebAccessTool",
                "target_skill": "web_research",
                "target_category": "web",
            }
        },
    )

    assert ok is False
    assert "Architecture contract failed" in error
