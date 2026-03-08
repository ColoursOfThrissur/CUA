from tools.tool_result import ToolResult, ResultStatus
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel
from core.tool_orchestrator import ToolOrchestrator


class DictParamTool:
    def __init__(self):
        self.name = "DictParamTool"
        self._caps = {
            "echo": ToolCapability(
                name="echo",
                description="echo",
                parameters=[
                    Parameter(name="text", type=ParameterType.STRING, description="text", required=True)
                ],
                returns="payload",
                safety_level=SafetyLevel.LOW,
                examples=[],
                dependencies=[],
            )
        }

    def get_capabilities(self):
        return self._caps

    def execute(self, operation, parameters):
        return ToolResult(
            tool_name=self.name,
            capability_name=operation,
            status=ResultStatus.SUCCESS,
            data={"text": parameters.get("text")},
        )


class KwargTool:
    def __init__(self):
        self.name = "KwargTool"
        self._caps = {
            "echo": ToolCapability(
                name="echo",
                description="echo",
                parameters=[
                    Parameter(name="text", type=ParameterType.STRING, description="text", required=True)
                ],
                returns="payload",
                safety_level=SafetyLevel.LOW,
                examples=[],
                dependencies=[],
            )
        }

    def get_capabilities(self):
        return self._caps

    def execute(self, operation, **kwargs):
        return ToolResult(
            tool_name=self.name,
            capability_name=operation,
            status=ResultStatus.SUCCESS,
            data={"text": kwargs.get("text")},
        )


class LegacyCapabilityTool:
    def __init__(self):
        self.name = "LegacyCapabilityTool"
        self._caps = {
            "echo": ToolCapability(
                name="echo",
                description="echo",
                parameters=[
                    Parameter(name="text", type=ParameterType.STRING, description="text", required=True)
                ],
                returns="payload",
                safety_level=SafetyLevel.LOW,
                examples=[],
                dependencies=[],
            )
        }

    def get_capabilities(self):
        return self._caps

    def execute_capability(self, capability_name, **kwargs):
        return ToolResult(
            tool_name=self.name,
            capability_name=capability_name,
            status=ResultStatus.SUCCESS,
            data={"text": kwargs.get("text")},
        )


class InternalTypeErrorTool:
    def __init__(self):
        self.name = "InternalTypeErrorTool"
        self._caps = {
            "create": ToolCapability(
                name="create",
                description="create",
                parameters=[
                    Parameter(name="contact_id", type=ParameterType.STRING, description="id", required=True)
                ],
                returns="payload",
                safety_level=SafetyLevel.LOW,
                examples=[],
                dependencies=[],
            )
        }

    def get_capabilities(self):
        return self._caps

    def execute(self, operation, parameters):
        # Simulate internal handler bug that raises TypeError.
        raise TypeError("isinstance() arg 2 must be a type, a tuple of types, or a union")


def test_tool_orchestrator_supports_dict_param_execute():
    orchestrator = ToolOrchestrator()
    tool = DictParamTool()
    result = orchestrator.execute_tool_step(tool, "DictParamTool", "echo", {"text": "hi"})
    assert result.success is True
    assert result.data == {"text": "hi"}


def test_tool_orchestrator_supports_kwarg_execute():
    orchestrator = ToolOrchestrator()
    tool = KwargTool()
    result = orchestrator.execute_tool_step(tool, "KwargTool", "echo", {"text": "hi"})
    assert result.success is True
    assert result.data == {"text": "hi"}


def test_tool_orchestrator_supports_legacy_execute_capability():
    orchestrator = ToolOrchestrator()
    tool = LegacyCapabilityTool()
    result = orchestrator.execute_tool_step(tool, "LegacyCapabilityTool", "echo", {"text": "hi"})
    assert result.success is True
    assert result.data == {"text": "hi"}


def test_tool_orchestrator_preserves_internal_type_errors_for_dict_signature():
    orchestrator = ToolOrchestrator()
    tool = InternalTypeErrorTool()
    result = orchestrator.execute_tool_step(tool, "InternalTypeErrorTool", "create", {"contact_id": "x"})
    assert result.success is False
    assert "isinstance() arg 2 must be a type" in (result.error or "")
    assert result.meta.get("exception") == "TypeError"
