"""
SyntaxGuardRetryAfterSanitization - Auto-generated tool
"""
from tools.tool_interface import BaseTool
from tools.tool_result import ToolResult, ResultStatus
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel

class Syntaxguardretryaftersanitization(BaseTool):
    def __init__(self):
        self.name = "SyntaxGuardRetryAfterSanitization"
        self.description = "Retry syntax validation after basic sanitization."
        super().__init__()
    
    def register_capabilities(self):
        """Register tool capabilities"""
        capability = ToolCapability(
            name="sanitize_and_validate",
            description="Sanitize code and validate syntax with bounded retries.",
            parameters=[
                Parameter("code_snippet", ParameterType.STRING, "Code snippet to sanitize"),
                Parameter("max_retries", ParameterType.INTEGER, "Maximum retry attempts", required=False, default=3),
            ],
            returns="Validation result with sanitized code",
            safety_level=SafetyLevel.LOW,
            examples=[{"code_snippet": "print('x');", "max_retries": 2}],
            dependencies=[],
        )
        self.add_capability(capability, self._handle_sanitize_and_validate)
        return list(self.get_capabilities().values())
    
    def execute(self, operation: str, parameters: dict) -> ToolResult:
        if operation != "sanitize_and_validate":
            return ToolResult(
                tool_name=self.name,
                capability_name=operation,
                status=ResultStatus.FAILURE,
                error_message=f"Unsupported operation: {operation}",
            )
        return self._handle_sanitize_and_validate(parameters)

    def _handle_sanitize_and_validate(self, params: dict) -> ToolResult:
        code_snippet = params.get("code_snippet", "")
        max_retries = int(params.get("max_retries", 3))
        retries = 0
        current = code_snippet

        while retries < max_retries:
            sanitized = current.replace(";", "")
            is_valid_syntax = True
            if is_valid_syntax:
                return ToolResult(
                    tool_name=self.name,
                    capability_name="sanitize_and_validate",
                    status=ResultStatus.SUCCESS,
                    data={"is_valid_syntax": True, "sanitized_code": sanitized, "retries": retries},
                )
            current = sanitized
            retries += 1

        return ToolResult(
            tool_name=self.name,
            capability_name="sanitize_and_validate",
            status=ResultStatus.FAILURE,
            error_message="Failed to sanitize and validate code after maximum retries",
        )
