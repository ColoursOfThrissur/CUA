"""
Shell Tool - Safe command execution
"""
import subprocess
import logging
from tools.tool_interface import BaseTool
from tools.tool_result import ToolResult, ResultStatus
logger = logging.getLogger(__name__)

class ShellTool(BaseTool):
    ALLOWED_COMMANDS = ['ls', 'dir', 'echo', 'cat', 'type', 'pwd', 'cd']

    def __init__(self):
        self.name = 'shell_tool'
        self.description = 'Execute safe shell commands'
        self.capabilities = ['execute']
        super().__init__()

    def register_capabilities(self):
        """Register shell execution capability"""
        from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel
        execute_cap = ToolCapability(name='execute', description='Execute safe shell commands', parameters=[Parameter('command', ParameterType.STRING, 'Command to execute'), Parameter('arguments', ParameterType.LIST, 'Arguments for the command (optional)')], returns='Command output', safety_level=SafetyLevel.HIGH, examples=[{'command': 'ls'}, {'command': 'pwd'}])
        self.add_capability(execute_cap, self._execute)

    def execute(self, operation: str, parameters: dict) -> ToolResult:
        if operation == 'execute':
            return self._execute(parameters)
        return ToolResult(tool_name=self.name, capability_name=operation, status=ResultStatus.FAILURE, error_message='Unknown operation')

    def _execute(self, params: dict) -> ToolResult:
        command = params.get('command')
        arguments = params.get('arguments', [])
        if not command:
            return self._handle_error('Command required')
        if not command in self.ALLOWED_COMMANDS:
            return self._handle_error(f"Command not allowed. Allowed: {', '.join(self.ALLOWED_COMMANDS)}")
        if arguments and (not all((isinstance(arg, str) for arg in arguments))):
            return self._handle_error('Arguments must be strings')
        try:
            result = subprocess.run([command] + arguments, capture_output=True, text=True, timeout=10)
            return ToolResult(tool_name=self.name, capability_name='execute', status=ResultStatus.SUCCESS, data={'stdout': result.stdout, 'stderr': result.stderr, 'returncode': result.returncode})
        except subprocess.TimeoutExpired:
            return self._handle_error('Command timed out')
        except Exception as e:
            return self._handle_error(str(e))

    def _handle_error(self, error_message: str) -> ToolResult:
        return ToolResult(
            tool_name=self.name,
            capability_name="execute",
            status=ResultStatus.FAILURE,
            error_message=error_message
        )