from planner.tool_calling import ToolCallingClient
from tools.tool_capability import SafetyLevel, ToolCapability
from tools.tool_interface import BaseTool
from api.server import _continue_tool_calling
from core.artifact_policy import choose_web_next_action


class _FakeRegistry:
    def __init__(self, tools=None):
        self._tools = tools or []

    @property
    def tools(self):
        return self._tools


class _FakeResponse:
    def __init__(self, payload):
        self.status_code = 200
        self._payload = payload

    def json(self):
        return self._payload


class _SimpleTool(BaseTool):
    tool_name = "SimpleTool"
    capability_name = "run"

    def register_capabilities(self):
        self.add_capability(
            ToolCapability(
                name=self.capability_name,
                description="do thing",
                parameters=[],
                returns="payload",
                safety_level=SafetyLevel.LOW,
                examples=[],
                dependencies=[],
            ),
            lambda: {"ok": True},
        )


class WebAccessTool(_SimpleTool):
    capability_name = "search_web"


class DatabaseQueryTool(_SimpleTool):
    capability_name = "query_logs"


def test_tool_calling_rejects_plain_text_for_actionable_requests(monkeypatch):
    def _fake_post(*args, **kwargs):
        return _FakeResponse(
            {
                "message": {
                    "content": "I cannot play videos, but I can help you find one.",
                    "tool_calls": [],
                }
            }
        )

    monkeypatch.setattr("planner.tool_calling.requests.post", _fake_post)

    client = ToolCallingClient("http://localhost:11434", "test-model", _FakeRegistry())
    success, tool_calls, response = client.call_with_tools("play expedition 33 trailer")

    assert success is False
    assert tool_calls is None
    assert response == "NO_TOOL_CALLS_FOR_ACTIONABLE_REQUEST"


def test_tool_calling_allows_clarification_response_for_ambiguous_request(monkeypatch):
    def _fake_post(*args, **kwargs):
        return _FakeResponse(
            {
                "message": {
                    "content": "Your request is unclear. Could you please provide more details about which AAA games you want?",
                    "tool_calls": [],
                }
            }
        )

    monkeypatch.setattr("planner.tool_calling.requests.post", _fake_post)

    client = ToolCallingClient("http://localhost:11434", "test-model", _FakeRegistry())
    success, tool_calls, response = client.call_with_tools("list some popular AAA action games")

    assert success is True
    assert tool_calls is None
    assert "provide more details" in response.lower()


def test_tool_calling_limits_definitions_to_allowed_tools():
    client = ToolCallingClient(
        "http://localhost:11434",
        "test-model",
        _FakeRegistry([WebAccessTool(), DatabaseQueryTool()]),
    )

    defs = client._build_tool_definitions(allowed_tools=["WebAccessTool"])
    names = {item["function"]["name"] for item in defs}

    assert "WebAccessTool_search_web" in names
    assert "DatabaseQueryTool_query_logs" not in names


def test_tool_calling_normalizes_wrapped_tool_call_shape(monkeypatch):
    def _fake_post(*args, **kwargs):
        return _FakeResponse(
            {
                "message": {
                    "content": '{"name":"WebAccessTool","arguments":{"operation":"search_web","parameters":{"query":"x"}}}',
                    "tool_calls": [],
                }
            }
        )

    monkeypatch.setattr("planner.tool_calling.requests.post", _fake_post)

    client = ToolCallingClient("http://localhost:11434", "test-model", _FakeRegistry([WebAccessTool()]))
    success, tool_calls, response = client.call_with_tools("search x")

    assert success is True
    assert response is None
    assert tool_calls == [{"tool": "WebAccessTool", "operation": "search_web", "parameters": {"query": "x"}}]


def test_tool_calling_rejects_disallowed_tool_calls(monkeypatch):
    def _fake_post(*args, **kwargs):
        return _FakeResponse(
            {
                "message": {
                    "content": '{"name":"ContextSummarizerTool_summarize_text","arguments":{"input_text":"x"}}',
                    "tool_calls": [],
                }
            }
        )

    monkeypatch.setattr("planner.tool_calling.requests.post", _fake_post)

    client = ToolCallingClient("http://localhost:11434", "test-model", _FakeRegistry([WebAccessTool(), DatabaseQueryTool()]))
    success, tool_calls, response = client.call_with_tools("continue", allowed_tools=["WebAccessTool"])

    assert success is False
    assert tool_calls is None
    assert response == "NO_ALLOWED_TOOL_CALLS"


def test_continue_tool_calling_restricts_web_tools_until_sources_exist(monkeypatch):
    captured = {}

    class _FakeCaller:
        def call_with_tools(self, user_message, conversation_history=None, skill_context=None, allowed_tools=None):
            captured["allowed_tools"] = allowed_tools
            return True, None, "done"

    _continue_tool_calling(
        _FakeCaller(),
        "find multiplayer aaa games",
        [],
        [{"tool": "WebAccessTool", "operation": "search_web", "data": {"content": "plain search text"}}],
        {
            "category": "web",
            "planning_context": {
                "preferred_tools": ["WebAccessTool", "ContextSummarizerTool"],
            },
        },
    )

    assert captured["allowed_tools"] == ["WebAccessTool"]


def test_continue_tool_calling_allows_summarizer_after_sources_exist(monkeypatch):
    captured = {}

    class _FakeCaller:
        def call_with_tools(self, user_message, conversation_history=None, skill_context=None, allowed_tools=None):
            captured["allowed_tools"] = allowed_tools
            return True, None, "done"

    _continue_tool_calling(
        _FakeCaller(),
        "find multiplayer aaa games",
        [],
        [{"tool": "WebAccessTool", "operation": "search_web", "data": {"sources": [{"url": "https://example.com"}]}}],
        {
            "category": "web",
            "planning_context": {
                "preferred_tools": ["WebAccessTool", "ContextSummarizerTool"],
            },
        },
    )

    assert "ContextSummarizerTool" in captured["allowed_tools"]


def test_artifact_policy_prefers_result_url():
    follow_up = choose_web_next_action([
        {
            "type": "search_results",
            "results": [
                {"title": "Game Rant", "url": "https://gamerant.com/best-coop-games"},
                {"title": "Google", "url": "https://google.com/search?q=x"},
            ],
        }
    ])

    assert follow_up == [{
        "tool": "WebAccessTool",
        "operation": "fetch_url",
        "parameters": {"url": "https://gamerant.com/best-coop-games", "mode": "auto"},
    }]


def test_continue_tool_calling_uses_synthetic_web_follow_up_before_summary():
    result = _continue_tool_calling(
        type("FakeCaller", (), {"call_with_tools": lambda *args, **kwargs: (True, None, "done")})(),
        "find multiplayer aaa games",
        [],
        [{
            "tool": "WebAccessTool",
            "operation": "search_web",
            "data": {"results": [{"title": "Game Rant", "url": "https://gamerant.com/best-coop-games"}]},
        }],
        {
            "category": "web",
            "planning_context": {
                "preferred_tools": ["WebAccessTool", "ContextSummarizerTool"],
            },
        },
    )

    assert result[0] is True
    assert result[1][0]["tool"] == "WebAccessTool"
    assert result[1][0]["operation"] == "fetch_url"
