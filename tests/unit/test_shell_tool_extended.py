import pytest
from tools.shell_tool import ShellTool
from tools.tool_result import ToolResult, ResultStatus

@pytest.fixture
def shell_tool():
    return ShellTool()

def test_execute_valid_command(shell_tool):
    result = shell_tool.execute("execute", {"command": "ls"})
    assert result.status == ResultStatus.SUCCESS
    assert isinstance(result.data["stdout"], str)
    assert not result.data["stderr"]

def test_execute_invalid_command(shell_tool):
    result = shell_tool.execute("execute", {"command": "rm"})
    assert result.status == ResultStatus.FAILURE
    assert "Command not allowed" in result.error_message

def test_execute_no_command_provided(shell_tool):
    result = shell_tool.execute("execute", {})
    assert result.status == ResultStatus.FAILURE
    assert "Command required" in result.error_message

def test_execute_with_arguments(shell_tool):
    result = shell_tool.execute("execute", {"command": "echo", "arguments": ["Hello, World!"]})
    assert result.status == ResultStatus.SUCCESS
    assert result.data["stdout"].strip() == "Hello, World!"
    assert not result.data["stderr"]

def test_execute_with_non_string_arguments(shell_tool):
    result = shell_tool.execute("execute", {"command": "echo", "arguments": [123]})
    assert result.status == ResultStatus.FAILURE
    assert "Arguments must be strings" in result.error_message

def test_execute_unknown_operation(shell_tool):
    result = shell_tool.execute("unknown", {})
    assert result.status == ResultStatus.FAILURE
    assert "Unknown operation" in result.error_message

def test_execute_timeout(shell_tool, monkeypatch):
    # Mock subprocess.run to simulate a timeout
    def mock_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=10)

    monkeypatch.setattr(subprocess, 'run', mock_run)
    
    result = shell_tool.execute("execute", {"command": "sleep", "arguments": ["15"]})
    assert result.status == ResultStatus.FAILURE
    assert "Timed out" in result.error_message

def test_execute_with_cd_command(shell_tool):
    # cd is not allowed, should fail
    result = shell_tool.execute("execute", {"command": "cd"})
    assert result.status == ResultStatus.FAILURE
    assert "Command not allowed" in result.error_message