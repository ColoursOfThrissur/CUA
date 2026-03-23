from planner.tool_calling import ToolCallingClient
from tools.tool_capability import SafetyLevel, ToolCapability
from tools.tool_interface import BaseTool


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
    pass


class HTTPTool(_SimpleTool):
    capability_name = "get"


class BrowserAutomationTool(_SimpleTool):
    capability_name = "open_and_navigate"


class _FakeRegistry:
    def __init__(self, tools):
        self._tools = tools

    @property
    def tools(self):
        return self._tools


def test_tool_definitions_hide_raw_web_transports_when_web_access_tool_exists():
    registry = _FakeRegistry([WebAccessTool(), HTTPTool(), BrowserAutomationTool()])
    client = ToolCallingClient("http://localhost:11434", "test-model", registry)

    defs = client._build_tool_definitions()
    names = {item["function"]["name"] for item in defs}

    assert "WebAccessTool_run" in names
    assert "HTTPTool_get" not in names
    assert "BrowserAutomationTool_open_and_navigate" not in names
