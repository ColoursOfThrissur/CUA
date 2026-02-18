
from tools.tool_interface import BaseTool
from tools.tool_result import ToolResult, ResultStatus
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel

class TestTool(BaseTool):
    def __init__(self):
        self.name = "test_tool"
        self.description = "Test tool for validation"
        self.capabilities = ["test_operation"]
        super().__init__()
    
    def register_capabilities(self):
        cap = ToolCapability(
            name="test_operation",
            description="Test operation",
            parameters=[Parameter("input", ParameterType.STRING, "Test input")],
            returns="Test output",
            safety_level=SafetyLevel.LOW,
            examples=[{"input": "test"}]
        )
        self.add_capability(cap, self._handle_test)
    
    def execute(self, operation: str, parameters: dict) -> ToolResult:
        if operation == "test_operation":
            return self._handle_test(parameters)
        return ToolResult(
            tool_name=self.name,
            capability_name=operation,
            status=ResultStatus.FAILURE,
            error_message="Unknown operation"
        )
    
    def _handle_test(self, params: dict) -> ToolResult:
        input_val = params.get("input", "")
        return ToolResult(
            tool_name=self.name,
            capability_name="test_operation",
            status=ResultStatus.SUCCESS,
            data={"output": f"Processed: {input_val}"}
        )
