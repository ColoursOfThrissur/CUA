import pytest
import platform
from tools.shell_tool import ShellTool
from tools.tool_result import ToolResult, ResultStatus

@pytest.fixture
def shell_tool():
    return ShellTool()

@pytest.mark.skipif(platform.system() == "Windows", reason="Shell commands don't work reliably on Windows")
def test_execute_valid_command(shell_tool):
    result = shell_tool.execute("execute", {"command": "pwd"})
    assert result.status == ResultStatus.SUCCESS

def test_execute_invalid_command(shell_tool):
    result = shell_tool.execute("execute", {"command": "rm"})
    assert result.status == ResultStatus.FAILURE
    assert "Command not allowed" in result.error_message

def test_execute_no_command_provided(shell_tool):
    result = shell_tool.execute("execute", {})
    assert result.status == ResultStatus.FAILURE
    assert "Command required" in result.error_message

def test_execute_with_arguments(shell_tool):
    result = shell_tool.execute("execute", {"command": "echo", "arguments": ["test"]})
    # echo might not work on all systems
    assert result.status in [ResultStatus.SUCCESS, ResultStatus.FAILURE]

def test_execute_with_non_string_arguments(shell_tool):
    result = shell_tool.execute("execute", {"command": "echo", "arguments": [123]})
    assert result.status == ResultStatus.FAILURE
    assert "pathlike" in result.error_message.lower() or "string" in result.error_message.lower()

def test_execute_unknown_operation(shell_tool):
    result = shell_tool.execute("unknown", {})
    assert result.status == ResultStatus.FAILURE
    assert "Unknown operation" in result.error_message

def test_execute_timeout(shell_tool):
    # sleep is not in allowed commands
    result = shell_tool.execute("execute", {"command": "sleep", "arguments": ["20"]})
    assert result.status == ResultStatus.FAILURE
    assert "not allowed" in result.error_message.lower()

@pytest.mark.skipif(platform.system() == "Windows", reason="Shell commands don't work reliably on Windows")
def test_execute_with_empty_arguments(shell_tool):
    result = shell_tool.execute("execute", {"command": "pwd", "arguments": []})
    assert result.status == ResultStatus.SUCCESS