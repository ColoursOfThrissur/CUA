"""
Atomic Applier - Apply updates atomically with rollback capability
"""
import subprocess
import shutil
import hashlib
from pathlib import Path
from typing import Optional, Tuple, Dict
from datetime import datetime

class AtomicApplier:
    def __init__(self, repo_path: str, backup_dir: str = "./backups"):
        self.repo_path = Path(repo_path)
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(exist_ok=True)
    
    def apply_update(self, patch_content: str, update_id: str) -> Tuple[bool, Optional[str]]:
        """Apply update atomically with protected files verification"""
        
        # Check if FILE_REPLACE format (not git diff)
        if patch_content.startswith("FILE_REPLACE:"):
            # Use direct file write instead of git apply
            return self._apply_file_replace(patch_content, update_id)
        
        # Verify protected files BEFORE applying
        protected_checksums = self._get_protected_checksums()
        
        # Create backup
        backup_path = self._create_backup(update_id)
        
        patch_file = None
        try:
            # Write patch
            patch_file = self.repo_path / f"update_{update_id}.patch"
            patch_file.write_text(patch_content)
            
            # Apply patch with timeout
            result = subprocess.run(
                ["git", "apply", "--check", patch_file.name],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                if patch_file.exists():
                    patch_file.unlink()
                return False, f"Patch validation failed: {result.stderr}"
            
            # Apply for real with timeout
            result = subprocess.run(
                ["git", "apply", patch_file.name],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if patch_file.exists():
                patch_file.unlink()
            
            if result.returncode != 0:
                # Rollback
                self.rollback(update_id)
                return False, f"Patch apply failed: {result.stderr}"
            
            # Verify protected files AFTER applying
            protected_checksums_after = self._get_protected_checksums()
            
            if protected_checksums != protected_checksums_after:
                # CRITICAL: Protected file was modified - rollback immediately
                self.rollback(update_id)
                return False, "CRITICAL: Protected file modification detected - update rolled back"
            
            # Commit with detailed message and timeout
            subprocess.run(["git", "add", "-A"], cwd=self.repo_path, timeout=30)
            
            # Extract files changed from patch
            changed_files = self._extract_changed_files(patch_content)
            commit_msg = f"Self-improvement: {update_id}\n\nFiles modified:\n" + "\n".join(f"- {f}" for f in changed_files)
            
            subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd=self.repo_path,
                timeout=30
            )
            
            return True, None
            
        except subprocess.TimeoutExpired:
            if patch_file and patch_file.exists():
                patch_file.unlink()
            self.rollback(update_id)
            return False, "Git operation timeout"
        except Exception as e:
            # Rollback on any error
            if patch_file and patch_file.exists():
                patch_file.unlink()
            self.rollback(update_id)
            return False, str(e)
    
    def rollback(self, update_id: str) -> bool:
        """Rollback to backup"""
        backup_path = self.backup_dir / f"backup_{update_id}"
        
        if not backup_path.exists():
            return False
        
        try:
            info_file = backup_path / "info.txt"
            if info_file.exists():
                # Git-based rollback
                info = info_file.read_text()
                commit_hash = info.split('commit: ')[1].split('\n')[0]
                subprocess.run(
                    ["git", "reset", "--hard", commit_hash],
                    cwd=self.repo_path,
                    check=True
                )
                return True
            return False
        except Exception:
            return False
    
    def rollback_manual_backup(self, backup_file: str) -> bool:
        """Rollback from manual .bak file"""
        backup_path = self.backup_dir / backup_file
        
        if not backup_path.exists():
            return False
        
        try:
            # Extract target file from backup filename
            # Format: filename.improvement_YYYYMMDD_HHMMSS.bak
            parts = backup_file.split('.')
            if len(parts) < 3:
                return False
            
            filename = parts[0] + '.py'
            
            # Find target file in project
            import os
            for root, dirs, files in os.walk(self.repo_path):
                if filename in files:
                    target = Path(root) / filename
                    shutil.copy2(backup_path, target)
                    return True
            
            return False
        except Exception:
            return False
    
    def _create_backup(self, update_id: str) -> Path:
        """Create backup before update"""
        
        backup_path = self.backup_dir / f"backup_{update_id}"
        
        # Store current commit hash
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            capture_output=True,
            text=True
        )
        
        commit_hash = result.stdout.strip()
        
        backup_info = backup_path / "info.txt"
        backup_path.mkdir(exist_ok=True)
        backup_info.write_text(f"commit: {commit_hash}\ntimestamp: {datetime.now().isoformat()}")
        
        return backup_path
    
    def _get_protected_checksums(self) -> Dict[str, str]:
        """Get checksums of all protected files"""
        from core.config_manager import get_config
        config = get_config()
        
        checksums = {}
        for protected_file in config.improvement.protected_files:
            file_path = self.repo_path / protected_file
            
            if not file_path.exists():
                continue
            
            try:
                content = file_path.read_bytes()
                checksums[protected_file] = hashlib.sha256(content).hexdigest()
            except Exception:
                pass
        
        return checksums
    
    def list_backups(self) -> list:
        """List available backups"""
        
        backups = []
        for backup_dir in self.backup_dir.glob("backup_*"):
            info_file = backup_dir / "info.txt"
            if info_file.exists():
                backups.append({
                    "update_id": backup_dir.name.replace("backup_", ""),
                    "info": info_file.read_text()
                })
        
        return backups
    
    def _extract_changed_files(self, patch_content: str) -> list:
        """Extract list of changed files from patch"""
        # Handle FILE_REPLACE format
        if patch_content.startswith("FILE_REPLACE:"):
            first_line = patch_content.split('\n')[0]
            file_path = first_line.replace("FILE_REPLACE:", "").strip()
            return [file_path]
        
        # Handle git diff format
        files = []
        for line in patch_content.split('\n'):
            if line.startswith('+++'):
                # Extract filename from +++ b/path/to/file
                file_path = line.split(' ')[1].replace('b/', '')
                if file_path != '/dev/null':
                    files.append(file_path)
        return files
    
    def _apply_file_replace(self, patch_content: str, update_id: str) -> Tuple[bool, Optional[str]]:
        """Apply FILE_REPLACE format patch"""
        import ast
        
        try:
            lines = patch_content.split('\n', 1)
            if len(lines) != 2:
                return False, "Invalid FILE_REPLACE format"
            
            file_path_str = lines[0].replace("FILE_REPLACE:", "").strip()
            new_content = lines[1]
            
            file_path = self.repo_path / file_path_str
            
            # Backup original
            backup_path = None
            if file_path.exists():
                backup_path = self.backup_dir / f"{file_path.name}.{update_id}.bak"
                shutil.copy2(file_path, backup_path)
            
            # Write new content
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(new_content, encoding='utf-8')
            
            # Validate syntax if Python file
            if file_path.suffix == '.py':
                try:
                    ast.parse(new_content)
                except SyntaxError as e:
                    # Rollback
                    if backup_path and backup_path.exists():
                        shutil.copy2(backup_path, file_path)
                    return False, f"Syntax error: {e}"
            
            return True, None
        except Exception as e:
            return False, f"FILE_REPLACE apply failed: {str(e)}"
