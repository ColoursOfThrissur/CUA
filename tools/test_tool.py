
from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel

class TestTool(BaseTool):
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
    
    def _handle_test(self, input: str) -> str:
        return f"Processed: {input}"
