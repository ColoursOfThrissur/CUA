"""
Shell Service - Provides shell command execution for tools
"""

import subprocess
from typing import Dict, Any, Optional, List


class ShellService:
    """Shell service for executing commands."""
    
    def __init__(self):
        self.timeout = 120
        self.allowed_commands = [
            'dir', 'ls', 'cat', 'echo', 'pwd', 'cd', 'mkdir', 'rm', 'cp', 'mv',
            'git', 'python', 'pip', 'npm', 'node', 'curl', 'wget', 'nvidia-smi'
        ]
    
    def execute(self, command: str, cwd: Optional[str] = None, env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Execute a shell command."""
        # Basic command validation
        cmd_parts = command.split()
        if not cmd_parts:
            return {
                "success": False,
                "error": "Empty command",
                "stdout": "",
                "stderr": "",
                "exit_code": 1
            }
        
        base_cmd = cmd_parts[0]
        if base_cmd not in self.allowed_commands:
            return {
                "success": False,
                "error": f"Command '{base_cmd}' not in allowlist",
                "stdout": "",
                "stderr": "",
                "exit_code": 1
            }
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": f"Command timed out after {self.timeout}s",
                "stdout": "",
                "stderr": "",
                "exit_code": 124
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "stdout": "",
                "stderr": "",
                "exit_code": 1
            }
    
    def is_allowed(self, command: str) -> bool:
        """Check if a command is allowed."""
        cmd_parts = command.split()
        if not cmd_parts:
            return False
        return cmd_parts[0] in self.allowed_commands
