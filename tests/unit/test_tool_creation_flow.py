from pathlib import Path

from core.tool_creation.validator import ToolValidator
from core.tool_creation.sandbox_runner import SandboxRunner
from core.expansion_mode import ExpansionMode


def _tool_code(class_name: str, register_body: str) -> str:
    return f"""from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel
from tools.tool_result import ToolResult, ResultStatus

class {class_name}(BaseTool):
    def __init__(self, orchestrator=None):
        self.description = "desc"
        self.services = orchestrator.get_services(self.__class__.__name__) if orchestrator else None
        super().__init__()

    def register_capabilities(self):
{register_body}

    def execute(self, operation: str, **kwargs) -> ToolResult:
        return self.execute_capability(operation, **kwargs)
"""


def test_validator_rejects_self_capabilities_assignment():
    validator = ToolValidator()
    code = _tool_code(
        "TaskSnapshotTool",
        "        self.capabilities = []\n",
    )
    ok, error = validator.validate(code, {"name": "TaskSnapshotTool"})
    assert ok is False
    assert "must not assign self.capabilities directly" in error


def test_validator_rejects_parameter_without_description():
    validator = ToolValidator()
    code = _tool_code(
        "TaskSnapshotTool",
        """        cap = ToolCapability(
            name="read",
            description="read",
            parameters=[Parameter(name="task_id", type=ParameterType.STRING, required=True)],
            returns="payload",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(cap, self._read)
""",
    ) + """
    def _read(self, **kwargs):
        return {"ok": True}
"""
    ok, error = validator.validate(code, {"name": "TaskSnapshotTool"})
    assert ok is False
    assert "must include description" in error


def test_validator_rejects_tool_capability_operation_field():
    validator = ToolValidator()
    code = _tool_code(
        "TaskSnapshotTool",
        """        cap = ToolCapability(
            operation="read",
            description="read",
            parameters=[Parameter(name="task_id", type=ParameterType.STRING, description="id")],
            returns="payload",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(cap, self._read)
""",
    ) + """
    def _read(self, **kwargs):
        return {"ok": True}
"""
    ok, error = validator.validate(code, {"name": "TaskSnapshotTool"})
    assert ok is False
    assert "must use name" in error


def test_sandbox_runner_fails_for_missing_file(tmp_path):
    expansion = ExpansionMode(enabled=True)
    expansion.experimental_dir = str(tmp_path / "missing_tools")
    runner = SandboxRunner(expansion)
    assert runner.run_sandbox("NoSuchTool") is False

