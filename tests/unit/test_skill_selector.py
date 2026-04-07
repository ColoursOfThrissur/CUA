from domain.entities.skill_models import SkillDefinition
from application.services.skill_selector import SkillSelector


class _FakeRegistry:
    def __init__(self, skills):
        self._skills = {skill.name: skill for skill in skills}

    def list_all(self):
        return list(self._skills.values())

    def get(self, name):
        return self._skills.get(name)

    def to_routing_context(self):
        rows = []
        for skill in self._skills.values():
            rows.append(
                {
                    "name": skill.name,
                    "category": skill.category,
                    "description": skill.description,
                    "trigger_examples": skill.trigger_examples,
                    "preferred_tools": skill.preferred_tools,
                }
            )
        return rows

    def get_learned_triggers(self, skill_name):
        return set()

    def get_tool_score(self, tool_name):
        return 0.5


class _FakeLLM:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def _call_llm(self, prompt, temperature=0.1, max_tokens=80, expect_json=True):
        self.calls += 1
        return self.payload

    def _extract_json(self, raw):
        import json

        return json.loads(raw)


class _FakeModelManager:
    def switch_to(self, mode):
        return None


def _skill(
    name,
    category,
    description,
    trigger_examples,
    preferred_tools,
    input_types,
    output_types,
    fallback_strategy="direct_tool_routing",
):
    return SkillDefinition(
        name=name,
        category=category,
        description=description,
        trigger_examples=trigger_examples,
        preferred_tools=preferred_tools,
        required_tools=[],
        preferred_connectors=[],
        input_types=input_types,
        output_types=output_types,
        verification_mode="output_validation",
        risk_level="medium",
        ui_renderer="default",
        fallback_strategy=fallback_strategy,
        skill_dir=f"skills/{name}",
        instructions_path=f"skills/{name}/SKILL.md",
        metadata={},
    )


def _registry():
    return _FakeRegistry(
        [
            _skill(
                "conversation",
                "conversation",
                "General chat and casual responses.",
                ["hello", "thanks"],
                [],
                ["message"],
                ["response"],
                fallback_strategy="direct_response",
            ),
            _skill(
                "computer_automation",
                "computer",
                "Desktop apps and local system automation.",
                ["open steam", "click on desktop", "find game playtime in steam"],
                ["SystemControlTool", "InputAutomationTool", "ScreenPerceptionTool"],
                ["local_task"],
                ["automation_result"],
                fallback_strategy="safe_direct_tool_routing",
            ),
            _skill(
                "system_health",
                "system",
                "Monitor system health and diagnose runtime issues.",
                ["check system health", "how many LLM calls per hour"],
                ["SystemHealthTool"],
                ["query", "hours"],
                ["health_report", "system_metrics"],
            ),
        ]
    )


def test_select_skill_uses_direct_conversation_fast_path_without_llm(monkeypatch):
    import shared.config.model_manager as model_manager_module

    monkeypatch.setattr(model_manager_module, "get_model_manager", lambda llm_client: _FakeModelManager())
    selector = SkillSelector()
    llm = _FakeLLM('{"skill_name":"computer_automation","confidence":0.99}')

    selection = selector.select_skill("hello", _registry(), llm)

    assert selection.matched is True
    assert selection.skill_name == "conversation"
    assert selection.reason == "direct_conversation_pattern"
    assert llm.calls == 0


def test_select_skill_uses_llm_first_for_substantive_steam_request(monkeypatch):
    import shared.config.model_manager as model_manager_module

    monkeypatch.setattr(model_manager_module, "get_model_manager", lambda llm_client: _FakeModelManager())
    selector = SkillSelector()
    llm = _FakeLLM('{"skill_name":"computer_automation","confidence":0.91}')

    selection = selector.select_skill(
        "can u open steam and find our how many hours i have played conquerors blade",
        _registry(),
        llm,
    )

    assert selection.matched is True
    assert selection.skill_name == "computer_automation"
    assert selection.reason == "llm_primary"
    assert llm.calls == 1


def test_select_skill_falls_back_to_keyword_when_llm_primary_is_unavailable(monkeypatch):
    import shared.config.model_manager as model_manager_module

    monkeypatch.setattr(model_manager_module, "get_model_manager", lambda llm_client: _FakeModelManager())
    selector = SkillSelector()
    llm = _FakeLLM('{"skill_name":"unknown_skill","confidence":0.10}')

    selection = selector.select_skill("open steam", _registry(), llm)

    assert selection.matched is True
    assert selection.skill_name == "computer_automation"
    assert selection.reason == "direct_obvious_request"
    assert llm.calls == 0


def test_select_skill_uses_keyword_fallback_after_low_confidence_llm_for_substantive_request(monkeypatch):
    import shared.config.model_manager as model_manager_module

    monkeypatch.setattr(model_manager_module, "get_model_manager", lambda llm_client: _FakeModelManager())
    selector = SkillSelector()
    llm = _FakeLLM('{"skill_name":"system_health","confidence":0.10}')

    selection = selector.select_skill(
        "open steam and list all the games in library",
        _registry(),
        llm,
    )

    assert selection.matched is True
    assert selection.skill_name == "computer_automation"
    assert selection.reason == "score_primary"
    assert llm.calls == 1
