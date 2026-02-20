"""Shell service wrapper for tools"""
import subprocess
from typing import Dict, Any

class ShellService:
    """Provides shell execution capabilities to tools"""
    
    def execute(self, command: str, timeout: int = 30) -> Dict[str, Any]:
        """Execute shell command"""
        try:
            result = subprocess.run(
                command,
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
            return {
                "stdout": "",
                "stderr": f"Command timed out after {timeout}s",
                "exit_code": -1,
                "success": False
            }
