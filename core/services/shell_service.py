"""Shell service wrapper for tools"""
import re
import subprocess
from typing import Dict, Any

# Commands tools are allowed to run via self.services.shell.execute()
ALLOWED_COMMANDS = {
    "ls", "dir", "pwd", "echo", "cat", "type",
    "python", "python3", "pip", "pip3",
    "git", "curl", "wget",
    "mkdir", "cp", "mv", "rm",
}

# Patterns that indicate shell injection / chaining attempts
_INJECTION_RE = re.compile(r'[;&|`]|>>?|\$\(')


class ShellService:
    """Provides shell execution capabilities to tools — allowlist enforced."""

    def execute(self, command: str, timeout: int = 30) -> Dict[str, Any]:
        """Execute shell command if base command is on the allowlist."""
        stripped = command.strip()

        # Block injection characters before anything else
        if _INJECTION_RE.search(stripped):
            return {"stdout": "", "stderr": "Shell injection characters not allowed", "exit_code": -1, "success": False}

        base_cmd = stripped.split()[0].lower() if stripped else ""
        if base_cmd not in ALLOWED_COMMANDS:
            return {"stdout": "", "stderr": f"Command '{base_cmd}' not in shell allowlist", "exit_code": -1, "success": False}

        try:
            result = subprocess.run(
                stripped,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "success": result.returncode == 0
            }
        except subprocess.TimeoutExpired:
            return {"stdout": "", "stderr": f"Command timed out after {timeout}s", "exit_code": -1, "success": False}
