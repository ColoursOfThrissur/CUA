from tools.capability_registry import CapabilityRegistry
from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, SafetyLevel

def test_register_tool():
    registry = CapabilityRegistry()

    class TestTool(BaseTool):
        def register_capabilities(self):
            self.add_capability(
                ToolCapability(
                    name="test_capability",
                    description="This is a test capability.",
                    parameters=[],
                    returns="payload",
                    safety_level=SafetyLevel.LOW,
                    examples=[],
                    dependencies=[],
                ),
                lambda: {"ok": True},
            )

    tool = TestTool()
    registry.register_tool(tool)

    assert len(registry._tools) == 1
    assert list(registry._tools.values())[0] is tool
    assert len(registry._capabilities) == 1
    assert list(registry._capabilities.values())[0].name == "test_capability"

def test_get_all_capabilities():
    registry = CapabilityRegistry()

    class TestTool1(BaseTool):
        def register_capabilities(self):
            self.add_capability(
                ToolCapability(
                    name="capability1",
                    description="Description 1",
                    parameters=[],
                    returns="payload",
                    safety_level=SafetyLevel.LOW,
                    examples=[],
                    dependencies=[],
                ),
                lambda: {"capability": 1},
            )
            self.add_capability(
                ToolCapability(
                    name="capability2",
                    description="Description 2",
                    parameters=[],
                    returns="payload",
                    safety_level=SafetyLevel.MEDIUM,
                    examples=[],
                    dependencies=[],
                ),
                lambda: {"capability": 2},
            )

    class TestTool2(BaseTool):
        def register_capabilities(self):
            self.add_capability(
                ToolCapability(
                    name="capability3",
                    description="Description 3",
                    parameters=[],
                    returns="payload",
                    safety_level=SafetyLevel.HIGH,
                    examples=[],
                    dependencies=[],
                ),
                lambda: {"capability": 3},
            )

    tool1 = TestTool1()
    tool2 = TestTool2()
    registry.register_tool(tool1)
    registry.register_tool(tool2)

    capabilities = registry.get_all_capabilities()
    assert len(capabilities) == 3
    assert "capability1" in capabilities
    assert "capability2" in capabilities
    assert "capability3" in capabilities

def test_get_capabilities_by_safety_level():
    registry = CapabilityRegistry()

    class TestTool(BaseTool):
        def register_capabilities(self):
            self.add_capability(
                ToolCapability(
                    name="low",
                    description="Description for low",
                    parameters=[],
                    returns="payload",
                    safety_level=SafetyLevel.LOW,
                    examples=[],
                    dependencies=[],
                ),
                lambda: {"level": "low"},
            )
            self.add_capability(
                ToolCapability(
                    name="medium",
                    description="Description for medium",
                    parameters=[],
                    returns="payload",
                    safety_level=SafetyLevel.MEDIUM,
                    examples=[],
                    dependencies=[],
                ),
                lambda: {"level": "medium"},
            )
            self.add_capability(
                ToolCapability(
                    name="high",
                    description="Description for high",
                    parameters=[],
                    returns="payload",
                    safety_level=SafetyLevel.HIGH,
                    examples=[],
                    dependencies=[],
                ),
                lambda: {"level": "high"},
            )

    tool = TestTool()
    registry.register_tool(tool)

    low_level_capabilities = registry.get_capabilities_by_safety_level(SafetyLevel.LOW)
    medium_level_capabilities = registry.get_capabilities_by_safety_level(SafetyLevel.MEDIUM)
    high_level_capabilities = registry.get_capabilities_by_safety_level(SafetyLevel.HIGH)

    assert set(low_level_capabilities.keys()) == {"low"}
    assert set(medium_level_capabilities.keys()) == {"low", "medium"}
    assert set(high_level_capabilities.keys()) == {"low", "medium", "high"}

def test_find_capabilities_for_task():
    registry = CapabilityRegistry()

    class TestTool(BaseTool):
        def register_capabilities(self):
            self.add_capability(
                ToolCapability(
                    name="capability1",
                    description="token_one",
                    parameters=[],
                    returns="payload",
                    safety_level=SafetyLevel.LOW,
                    examples=[],
                    dependencies=[],
                ),
                lambda: {"c": 1},
            )
            self.add_capability(
                ToolCapability(
                    name="capability2",
                    description="token_two",
                    parameters=[],
                    returns="payload",
                    safety_level=SafetyLevel.MEDIUM,
                    examples=[],
                    dependencies=[],
                ),
                lambda: {"c": 2},
            )
            self.add_capability(
                ToolCapability(
                    name="capability3",
                    description="token_three",
                    parameters=[],
                    returns="payload",
                    safety_level=SafetyLevel.HIGH,
                    examples=[],
                    dependencies=[],
                ),
                lambda: {"c": 3},
            )

    tool = TestTool()
    registry.register_tool(tool)

    assert registry.find_capabilities_for_task("test task mentioning token_one") == ["capability1"]
    assert registry.find_capabilities_for_task("test task mentioning token_two") == ["capability2"]
    assert registry.find_capabilities_for_task("test task mentioning token_three") == ["capability3"]

def test_execute_capability():
    class TestTool(BaseTool):
        def register_capabilities(self):
            self.add_capability(
                ToolCapability(
                    name="test_capability",
                    description="test",
                    parameters=[],
                    returns="payload",
                    safety_level=SafetyLevel.LOW,
                    examples=[],
                    dependencies=[],
                ),
                lambda: {"done": True},
            )

    registry = CapabilityRegistry()
    tool = TestTool()
    registry.register_tool(tool)

    result = registry.execute_capability("test_capability")
    assert result.is_success()
    assert result.data == {"done": True}


def test_execute_tool_capability_avoids_name_collision():
    class HttpLikeTool(BaseTool):
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

    class NoteLikeTool(BaseTool):
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

    registry = CapabilityRegistry()
    registry.register_tool(HttpLikeTool())
    registry.register_tool(NoteLikeTool())

    result = registry.execute_tool_capability("HttpLikeTool", "get")

    assert result.is_success()
    assert result.data == {"source": "http"}

def test_get_capability_performance():
    class TestTool(BaseTool):
        def register_capabilities(self):
            self.add_capability(
                ToolCapability(
                    name="test_capability",
                    description="test",
                    parameters=[],
                    returns="payload",
                    safety_level=SafetyLevel.LOW,
                    examples=[],
                    dependencies=[],
                ),
                lambda: {"done": True},
            )

    registry = CapabilityRegistry()
    tool = TestTool()
    registry.register_tool(tool)

    registry.execute_capability("test_capability")
    performance = registry.get_capability_performance("test_capability")
    assert performance["success_rate"] == 1.0
    assert performance["total_calls"] == 1
    assert performance["recent_failures"] == []

def test_to_llm_context():
    class TestTool(BaseTool):
        def register_capabilities(self):
            self.add_capability(
                ToolCapability(
                    name="capability1",
                    description="Description for capability 1",
                    parameters=[],
                    returns="payload",
                    safety_level=SafetyLevel.LOW,
                    examples=[],
                    dependencies=[],
                ),
                lambda: {"c": 1},
            )
            self.add_capability(
                ToolCapability(
                    name="capability2",
                    description="Description for capability 2",
                    parameters=[],
                    returns="payload",
                    safety_level=SafetyLevel.MEDIUM,
                    examples=[],
                    dependencies=[],
                ),
                lambda: {"c": 2},
            )
            self.add_capability(
                ToolCapability(
                    name="capability3",
                    description="Description for capability 3",
                    parameters=[],
                    returns="payload",
                    safety_level=SafetyLevel.HIGH,
                    examples=[],
                    dependencies=[],
                ),
                lambda: {"c": 3},
            )

    registry = CapabilityRegistry()
    tool = TestTool()
    registry.register_tool(tool)

    context = registry.to_llm_context(max_safety_level=SafetyLevel.HIGH)
    assert "Available capabilities:" in context
    assert "capability1" in context
    assert "capability2" in context
    assert "capability3" in context
