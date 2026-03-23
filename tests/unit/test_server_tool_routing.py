from tools.capability_registry import CapabilityRegistry
from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, SafetyLevel


class HTTPTool(BaseTool):
    def register_capabilities(self):
        self.add_capability(
            ToolCapability(
                name="get",
                description="http get",
                parameters=[],
                returns="payload",
                safety_level=SafetyLevel.LOW,
                examples=[],
                dependencies=[],
            ),
            lambda: {"source": "http"},
        )


class LocalRunNoteTool(BaseTool):
    def register_capabilities(self):
        self.add_capability(
            ToolCapability(
                name="get",
                description="note get",
                parameters=[],
                returns="payload",
                safety_level=SafetyLevel.LOW,
                examples=[],
                dependencies=[],
            ),
            lambda: {"source": "note"},
        )


def test_explicit_tool_execution_uses_http_tool_not_colliding_get():
    registry = CapabilityRegistry()
    registry.register_tool(HTTPTool())
    registry.register_tool(LocalRunNoteTool())

    result = registry.execute_tool_capability("HTTPTool", "get")

    assert result.is_success()
    assert result.data == {"source": "http"}


class DatabaseLikeTool(BaseTool):
    def register_capabilities(self):
        self.add_capability(
            ToolCapability(
                name="analyze_tool_performance",
                description="analyze tool performance",
                parameters=[],
                returns="payload",
                safety_level=SafetyLevel.LOW,
                examples=[],
                dependencies=[],
            ),
            lambda **kwargs: {"received_tool_name": kwargs.get("tool_name")},
        )


def test_explicit_tool_execution_allows_payload_tool_name_parameter():
    registry = CapabilityRegistry()
    registry.register_tool(DatabaseLikeTool())

    result = registry.execute_tool_capability(
        "DatabaseLikeTool",
        "analyze_tool_performance",
        tool_name="WebAccessTool",
    )

    assert result.is_success()
    assert result.data == {"received_tool_name": "WebAccessTool"}
