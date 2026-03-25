"""
Shell Tool - Safe command execution with full control.
"""
import subprocess
import logging
import os
import tempfile

from tools.tool_interface import BaseTool
from tools.tool_result import ToolResult, ResultStatus
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel

logger = logging.getLogger(__name__)


class ShellTool(BaseTool):
    """Execute shell commands safely with allowlist enforcement."""

    ALLOWED_COMMANDS = [
        # navigation / listing
        "ls", "dir", "pwd", "cd", "find", "tree",
        # file ops (read-only style)
        "cat", "type", "head", "tail", "wc", "grep", "sort", "uniq", "diff",
        # process / system info
        "echo", "env", "set", "whoami", "hostname", "date", "uptime",
        "ps", "tasklist", "top",
        # python / pip
        "python", "python3", "pip", "pip3",
        # node / npx — for MCP server management
        "node", "npx",
        # git (read-only)
        "git",
        # network info
        "ping", "curl", "wget",
        # misc
        "mkdir", "touch", "cp", "mv", "rm",
    ]

    def __init__(self, orchestrator=None):
        self.description = "Execute safe shell commands with timeout and working directory control."
        super().__init__()
        if orchestrator:
            self.services = orchestrator.get_services(self.__class__.__name__)

    def register_capabilities(self):
        self.add_capability(ToolCapability(
            name="execute",
            description="Execute a single shell command from the allowed list.",
            parameters=[
                Parameter("command", ParameterType.STRING, "Command to run (must be in allowed list)"),
                Parameter("arguments", ParameterType.LIST, "List of string arguments for the command", required=False),
                Parameter("working_dir", ParameterType.STRING, "Working directory for the command", required=False),
                Parameter("timeout", ParameterType.INTEGER, "Timeout in seconds. Default: 30", required=False),
                Parameter("env", ParameterType.DICT, "Extra environment variables to set", required=False),
            ],
            returns="Dict with stdout, stderr, returncode.",
            safety_level=SafetyLevel.HIGH,
            examples=[{"command": "python", "arguments": ["-m", "pytest", "-q"]}],
        ), self._handle_execute)

        self.add_capability(ToolCapability(
            name="run_script",
            description="Write a multi-line shell/Python script to a temp file and execute it.",
            parameters=[
                Parameter("script", ParameterType.STRING, "Script content to execute"),
                Parameter("interpreter", ParameterType.STRING, "Interpreter: python, python3, bash, sh, cmd. Default: python", required=False),
                Parameter("working_dir", ParameterType.STRING, "Working directory", required=False),
                Parameter("timeout", ParameterType.INTEGER, "Timeout in seconds. Default: 60", required=False),
            ],
            returns="Dict with stdout, stderr, returncode.",
            safety_level=SafetyLevel.HIGH,
            examples=[{"script": "print('hello')", "interpreter": "python"}],
        ), self._handle_run_script)

        self.add_capability(ToolCapability(
            name="pipe",
            description="Run two commands piped together: cmd1 | cmd2.",
            parameters=[
                Parameter("command1", ParameterType.STRING, "First command"),
                Parameter("args1", ParameterType.LIST, "Arguments for first command", required=False),
                Parameter("command2", ParameterType.STRING, "Second command"),
                Parameter("args2", ParameterType.LIST, "Arguments for second command", required=False),
                Parameter("working_dir", ParameterType.STRING, "Working directory", required=False),
                Parameter("timeout", ParameterType.INTEGER, "Timeout in seconds. Default: 30", required=False),
            ],
            returns="Dict with stdout, stderr, returncode.",
            safety_level=SafetyLevel.HIGH,
            examples=[{"command1": "echo", "args1": ["hello world"], "command2": "grep", "args2": ["hello"]}],
        ), self._handle_pipe)

        self.add_capability(ToolCapability(
            name="get_environment",
            description="Get current environment variables, optionally filtered by prefix.",
            parameters=[
                Parameter("prefix", ParameterType.STRING, "Filter variables starting with this prefix", required=False),
            ],
            returns="Dict of environment variable names and values.",
            safety_level=SafetyLevel.LOW,
            examples=[{"prefix": "PATH"}],
        ), self._handle_get_environment)

        self.add_capability(ToolCapability(
            name="which",
            description="Check if a command/program is available on the system PATH.",
            parameters=[
                Parameter("command", ParameterType.STRING, "Command name to look up"),
            ],
            returns="Dict with found (bool) and path.",
            safety_level=SafetyLevel.LOW,
            examples=[{"command": "python"}],
        ), self._handle_which)

    # ── Handlers ──────────────────────────────────────────────────────────────

    def _handle_execute(self, command: str, arguments: list = None, working_dir: str = None,
                        timeout: int = 30, env: dict = None, **kwargs) -> dict:
        if not command:
            raise ValueError("command is required")
        base = command.split()[0] if " " in command else command
        if base not in self.ALLOWED_COMMANDS:
            raise ValueError(f"Command '{base}' not allowed. Allowed: {', '.join(sorted(self.ALLOWED_COMMANDS))}")
        args = [command] + (arguments or [])
        merged_env = {**os.environ, **(env or {})}
        try:
            result = subprocess.run(
                args, capture_output=True, text=True,
                timeout=timeout or 30,
                cwd=working_dir or None,
                env=merged_env,
            )
            return {"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Command timed out after {timeout}s")

    def _handle_run_script(self, script: str, interpreter: str = "python",
                           working_dir: str = None, timeout: int = 60, **kwargs) -> dict:
        if not script:
            raise ValueError("script is required")
        allowed_interpreters = {"python", "python3", "bash", "sh", "cmd"}
        interp = (interpreter or "python").lower()
        if interp not in allowed_interpreters:
            raise ValueError(f"Interpreter '{interp}' not allowed. Use: {', '.join(sorted(allowed_interpreters))}")
        ext = ".py" if interp in {"python", "python3"} else (".bat" if interp == "cmd" else ".sh")
        with tempfile.NamedTemporaryFile(mode="w", suffix=ext, delete=False, encoding="utf-8") as f:
            f.write(script)
            tmp_path = f.name
        try:
            result = subprocess.run(
                [interp, tmp_path], capture_output=True, text=True,
                timeout=timeout or 60,
                cwd=working_dir or None,
            )
            return {"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Script timed out after {timeout}s")
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    def _handle_pipe(self, command1: str, args1: list = None, command2: str = None,
                     args2: list = None, working_dir: str = None, timeout: int = 30, **kwargs) -> dict:
        for cmd in [command1, command2]:
            if cmd and cmd not in self.ALLOWED_COMMANDS:
                raise ValueError(f"Command '{cmd}' not allowed.")
        p1 = subprocess.Popen(
            [command1] + (args1 or []), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=working_dir or None,
        )
        p2 = subprocess.Popen(
            [command2] + (args2 or []), stdin=p1.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=working_dir or None,
        )
        p1.stdout.close()
        try:
            stdout, stderr = p2.communicate(timeout=timeout or 30)
            return {"stdout": stdout.decode("utf-8", errors="replace"), "stderr": stderr.decode("utf-8", errors="replace"), "returncode": p2.returncode}
        except subprocess.TimeoutExpired:
            p2.kill()
            raise RuntimeError(f"Pipe timed out after {timeout}s")

    def _handle_get_environment(self, prefix: str = None, **kwargs) -> dict:
        env = dict(os.environ)
        if prefix:
            env = {k: v for k, v in env.items() if k.startswith(prefix)}
        return env

    def _handle_which(self, command: str, **kwargs) -> dict:
        import shutil
        path = shutil.which(command)
        return {"found": path is not None, "path": path, "command": command}

    def execute(self, operation: str, parameters: dict) -> ToolResult:
        if operation in self._capabilities:
            return self.execute_capability(operation, **parameters)
        return ToolResult(
            tool_name=self.name, capability_name=operation,
            status=ResultStatus.FAILURE, error_message=f"Unknown operation: {operation}",
        )
