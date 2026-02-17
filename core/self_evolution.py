"""
Self-Evolution System - Sandboxed capability updates with automated testing
"""

import os
import shutil
import subprocess
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime

@dataclass
class CapabilityUpdate:
    capability_name: str
    code: str
    test_code: str
    version: str
    author: str = "system"

@dataclass
class UpdateResult:
    success: bool
    capability_name: str
    version: str
    tests_passed: bool
    error: Optional[str] = None
    rollback_available: bool = False

class SandboxedEvolution:
    """Manages safe capability updates with testing and rollback"""
    
    def __init__(self, tools_dir: str = "./tools", sandbox_dir: str = "./sandbox", backup_dir: str = "./backups"):
        self.tools_dir = Path(tools_dir)
        self.sandbox_dir = Path(sandbox_dir)
        self.backup_dir = Path(backup_dir)
        self.sandbox_dir.mkdir(exist_ok=True)
        self.backup_dir.mkdir(exist_ok=True)
    
    def propose_update(self, update: CapabilityUpdate) -> UpdateResult:
        """Propose capability update with automated validation"""
        
        # Step 1: Create sandbox
        sandbox_path = self._create_sandbox()
        
        try:
            # Step 2: Write new capability to sandbox
            capability_file = sandbox_path / f"{update.capability_name}_tool.py"
            capability_file.write_text(update.code)
            
            # Step 3: Write tests to sandbox
            test_file = sandbox_path / f"test_{update.capability_name}.py"
            test_file.write_text(update.test_code)
            
            # Step 4: Run tests in sandbox
            tests_passed, error = self._run_sandbox_tests(test_file)
            
            if not tests_passed:
                return UpdateResult(
                    success=False,
                    capability_name=update.capability_name,
                    version=update.version,
                    tests_passed=False,
                    error=f"Tests failed: {error}"
                )
            
            # Step 5: Backup existing capability
            backup_path = self._backup_capability(update.capability_name, update.version)
            
            # Step 6: Deploy to production
            self._deploy_capability(capability_file, update.capability_name)
            
            return UpdateResult(
                success=True,
                capability_name=update.capability_name,
                version=update.version,
                tests_passed=True,
                rollback_available=backup_path is not None
            )
            
        except Exception as e:
            return UpdateResult(
                success=False,
                capability_name=update.capability_name,
                version=update.version,
                tests_passed=False,
                error=str(e)
            )
        finally:
            # Cleanup sandbox
            self._cleanup_sandbox(sandbox_path)
    
    def rollback_capability(self, capability_name: str, version: str) -> bool:
        """Rollback capability to previous version"""
        
        backup_file = self.backup_dir / f"{capability_name}_v{version}.py"
        
        if not backup_file.exists():
            return False
        
        target_file = self.tools_dir / f"{capability_name}_tool.py"
        shutil.copy2(backup_file, target_file)
        
        return True
    
    def _create_sandbox(self) -> Path:
        """Create isolated sandbox directory"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        sandbox_path = self.sandbox_dir / f"sandbox_{timestamp}"
        sandbox_path.mkdir(exist_ok=True)
        
        # Copy core dependencies
        for dep in ["core", "tools"]:
            src = Path(dep)
            if src.exists():
                shutil.copytree(src, sandbox_path / dep, dirs_exist_ok=True)
        
        return sandbox_path
    
    def _run_sandbox_tests(self, test_file: Path) -> tuple[bool, Optional[str]]:
        """Run tests in sandbox environment"""
        
        try:
            result = subprocess.run(
                ["python", test_file.name],
                cwd=test_file.parent,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                return True, None
            else:
                return False, result.stderr or result.stdout
                
        except subprocess.TimeoutExpired:
            return False, "Test timeout"
        except Exception as e:
            return False, str(e)
    
    def _backup_capability(self, capability_name: str, version: str) -> Optional[Path]:
        """Backup existing capability before update"""
        
        source_file = self.tools_dir / f"{capability_name}_tool.py"
        
        if not source_file.exists():
            return None
        
        backup_file = self.backup_dir / f"{capability_name}_v{version}.py"
        shutil.copy2(source_file, backup_file)
        
        return backup_file
    
    def _deploy_capability(self, sandbox_file: Path, capability_name: str):
        """Deploy capability from sandbox to production"""
        
        target_file = self.tools_dir / f"{capability_name}_tool.py"
        shutil.copy2(sandbox_file, target_file)
    
    def _cleanup_sandbox(self, sandbox_path: Path):
        """Remove sandbox directory"""
        if sandbox_path.exists():
            shutil.rmtree(sandbox_path)
    
    def get_capability_version(self, capability_name: str) -> Optional[str]:
        """Get current version of capability"""
        
        capability_file = self.tools_dir / f"{capability_name}_tool.py"
        
        if not capability_file.exists():
            return None
        
        # Calculate hash as version
        content = capability_file.read_bytes()
        return hashlib.sha256(content).hexdigest()[:8]
    
    def list_backups(self, capability_name: str) -> list[str]:
        """List available backups for capability"""
        
        backups = []
        for backup_file in self.backup_dir.glob(f"{capability_name}_v*.py"):
            backups.append(backup_file.stem)
        
        return sorted(backups)
