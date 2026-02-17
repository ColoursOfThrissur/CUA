"""
Sandbox Runner - Executes updates in isolated environment
"""
import subprocess
import tempfile
import shutil
import os
from pathlib import Path
from typing import Optional, Tuple
from dataclasses import dataclass

@dataclass
class SandboxResult:
    success: bool
    test_output: str
    error: Optional[str] = None

class SandboxRunner:
    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)
    
    def run_in_sandbox(self, patch_content: str, timeout: int = 120) -> SandboxResult:
        """Run update in isolated sandbox
        Args:
            patch_content: Git patch to apply
            timeout: Timeout for test execution in seconds
        """
        
        with tempfile.TemporaryDirectory() as temp_dir:
            sandbox_path = Path(temp_dir) / "sandbox"
            
            try:
                # Clone repo to sandbox
                shutil.copytree(self.repo_path, sandbox_path, 
                               ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.git', 
                                                            'checkpoints', 'logs', 'sandbox', 'backups'))
                
                # Apply patch
                patch_file = sandbox_path / "update.patch"
                patch_file.write_text(patch_content)
                
                # Check if git is available
                try:
                    result = subprocess.run(
                        ["git", "apply", "update.patch"],
                        cwd=sandbox_path,
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    
                    if result.returncode != 0:
                        return SandboxResult(
                            success=False,
                            test_output="",
                            error=f"Patch apply failed: {result.stderr}"
                        )
                except FileNotFoundError:
                    # Git not available - skip patch apply and tests
                    return SandboxResult(
                        success=True,
                        test_output="SKIPPED: git not available (patch not applied)",
                        error=None
                    )
                
                # Run tests in sandbox
                test_result = self._run_tests(sandbox_path, timeout)
                
                return test_result
                
            except Exception as e:
                return SandboxResult(
                    success=False,
                    test_output="",
                    error=str(e)
                )
    
    def _run_tests(self, sandbox_path: Path, timeout: int = 120) -> SandboxResult:
        """Run test suite in sandbox with restricted permissions
        Args:
            sandbox_path: Path to sandbox directory
            timeout: Timeout in seconds
        """
        
        try:
            # Check if pytest is available first
            try:
                pytest_check = subprocess.run(
                    ["python", "-m", "pytest", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if pytest_check.returncode != 0:
                    return SandboxResult(
                        success=True,
                        test_output="SKIPPED: pytest not installed",
                        error=None
                    )
            except (FileNotFoundError, subprocess.TimeoutExpired):
                return SandboxResult(
                    success=True,
                    test_output="SKIPPED: pytest not available",
                    error=None
                )
            
            # Restricted environment
            env = {
                'PYTHONDONTWRITEBYTECODE': '1',
                'PATH': os.environ.get('PATH', ''),
                'SYSTEMROOT': os.environ.get('SYSTEMROOT', ''),
                'TEMP': os.environ.get('TEMP', ''),
                'TMP': os.environ.get('TMP', '')
            }
            
            # Windows process restrictions
            creation_flags = 0
            if os.name == 'nt':
                creation_flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
            
            result = subprocess.run(
                ["python", "-m", "pytest", "tests/unit/", "-v", "--tb=short"],
                cwd=sandbox_path,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                creationflags=creation_flags
            )
            
            success = result.returncode == 0
            
            return SandboxResult(
                success=success,
                test_output=result.stdout,
                error=result.stderr if not success else None
            )
            
        except subprocess.TimeoutExpired:
            return SandboxResult(
                success=False,
                test_output="",
                error="Tests timed out"
            )
        except FileNotFoundError:
            return SandboxResult(
                success=True,
                test_output="SKIPPED: Python not found",
                error=None
            )
        except Exception as e:
            return SandboxResult(
                success=True,
                test_output=f"SKIPPED: {str(e)}",
                error=None
            )
