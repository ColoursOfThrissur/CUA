import pytest
from tools.capability_registry import CapabilityRegistry, BaseTool, ToolCapability, SafetyLevel, ToolResult, ResultStatus

def test_register_tool():
    registry = CapabilityRegistry()

    class TestTool(BaseTool):
        def get_capabilities(self):
            return {
                "test_capability": ToolCapability("Test Capability", SafetyLevel.LOW, "This is a test capability.")
            }

    tool = TestTool()
    registry.register_tool(tool)

    assert len(registry._tools) == 1
    assert list(registry._tools.values())[0] is tool
    assert len(registry._capabilities) == 1
    assert list(registry._capabilities.values())[0].name == "test_capability"

def test_get_all_capabilities():
    registry = CapabilityRegistry()

    class TestTool1(BaseTool):
        def get_capabilities(self):
            return {
                "capability1": ToolCapability("Capability 1", SafetyLevel.LOW, "Description 1"),
                "capability2": ToolCapability("Capability 2", SafetyLevel.MEDIUM, "Description 2")
            }

    class TestTool2(BaseTool):
        def get_capabilities(self):
            return {
                "capability3": ToolCapability("Capability 3", SafetyLevel.HIGH, "Description 3")
            }

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
        def get_capabilities(self):
            return {
                "low": ToolCapability("Low", SafetyLevel.LOW, "Description for low"),
                "medium": ToolCapability("Medium", SafetyLevel.MEDIUM, "Description for medium"),
                "high": ToolCapability("High", SafetyLevel.HIGH, "Description for high")
            }

    tool = TestTool()
    registry.register_tool(tool)

    low_level_capabilities = registry.get_capabilities_by_safety_level(SafetyLevel.LOW)
    medium_level_capabilities = registry.get_capabilities_by_safety_level(SafetyLevel.MEDIUM)
    high_level_capabilities = registry.get_capabilities_by_safety_level(SafetyLevel.HIGH)

    assert len(low_level_capabilities) == 1
    assert len(medium_level_capabilities) == 1
    assert len(high_level_capabilities) == 1
    assert low_level_capabilities["low"].name == "low"
    assert medium_level_capabilities["medium"].name == "medium"
    assert high_level_capabilities["high"].name == "high"

def test_find_capabilities_for_task():
    registry = CapabilityRegistry()

    class TestTool(BaseTool):
        def get_capabilities(self):
            return {
                "capability1": ToolCapability("Capability 1", SafetyLevel.LOW, "Description for capability 1"),
                "capability2": ToolCapability("Capability 2", SafetyLevel.MEDIUM, "Description for capability 2"),
                "capability3": ToolCapability("Capability 3", SafetyLevel.HIGH, "Description for capability 3")
            }

    tool = TestTool()
    registry.register_tool(tool)

    assert registry.find_capabilities_for_task("test task with description containing capability 1") == ["capability1"]
    assert registry.find_capabilities_for_task("test task with description containing capability 2") == ["capability2"]
    assert registry.find_capabilities_for_task("test task with description containing capability 3") == ["capability3"]

def test_execute_capability():
    class TestTool(BaseTool):
        def execute_capability(self, capability_name, **kwargs):
            if capability_name == "test_capability":
                return ToolResult("Test Tool", "test_capability", ResultStatus.SUCCESS, execution_time=1.0)
            else:
                return ToolResult("Test Tool", capability_name, ResultStatus.FAILURE, error_message="Capability not found")

    registry = CapabilityRegistry()
    tool = TestTool()
    registry.register_tool(tool)

    result = registry.execute_capability("test_capability")
    assert result.is_success()
    assert result.execution_time == 1.0

def test_get_capability_performance():
    class TestTool(BaseTool):
        def execute_capability(self, capability_name, **kwargs):
            if capability_name == "test_capability":
                return ToolResult("Test Tool", "test_capability", ResultStatus.SUCCESS, execution_time=1.0)
            else:
                return ToolResult("Test Tool", capability_name, ResultStatus.FAILURE, error_message="Capability not found")

    registry = CapabilityRegistry()
    tool = TestTool()
    registry.register_tool(tool)

    performance = registry.get_capability_performance("test_capability")
    assert performance["success_rate"] == 1.0
    assert performance["avg_time"] == 1.0
    assert performance["total_calls"] == 1
    assert performance["recent_failures"] == []

def test_to_llm_context():
    class TestTool(BaseTool):
        def get_capabilities(self):
            return {
                "capability1": ToolCapability("Capability 1", SafetyLevel.LOW, "Description for capability 1"),
                "capability2": ToolCapability("Capability 2", SafetyLevel.MEDIUM, "Description for capability 2"),
                "capability3": ToolCapability("Capability 3", SafetyLevel.HIGH, "Description for capability 3")
            }

    registry = CapabilityRegistry()
    tool = TestTool()
    registry.register_tool(tool)

    context = registry.to_llm_context()
    assert "Available capabilities:" in context
    assert "Capability 1" in context
    assert "Capability 2" in context
    assert "Capability 3" in context