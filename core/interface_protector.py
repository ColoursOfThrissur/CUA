"""
Interface Protector - Prevent breaking core interfaces
"""
import ast
import hashlib
from pathlib import Path
from typing import Dict, Optional

class InterfaceProtector:
    PROTECTED_INTERFACES = [
        "tools/tool_interface.py",
        "tools/tool_result.py",
        "core/immutable_brain_stem.py"
    ]
    
    def __init__(self, repo_path: str = "."):
        self.repo_path = Path(repo_path)
        self.signatures = {}
    
    def snapshot(self, file_path: str) -> None:
        """Snapshot public method signatures"""
        full_path = self.repo_path / file_path
        if not full_path.exists():
            return
        
        try:
            code = full_path.read_text(encoding='utf-8')
            tree = ast.parse(code)
            
            signatures = []
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef):
                            # Get signature
                            args = [a.arg for a in item.args.args]
                            sig = f"{item.name}({','.join(args)})"
                            signatures.append(sig)
            
            self.signatures[file_path] = hashlib.sha256('\n'.join(sorted(signatures)).encode()).hexdigest()
        except:
            pass
    
    def verify(self, file_path: str, new_code: str) -> tuple[bool, Optional[str]]:
        """Verify signatures unchanged"""
        if file_path not in self.signatures:
            return True, None
        
        try:
            tree = ast.parse(new_code)
            new_signatures = []
            
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef):
                            args = [a.arg for a in item.args.args]
                            sig = f"{item.name}({','.join(args)})"
                            new_signatures.append(sig)
            
            new_hash = hashlib.sha256('\n'.join(sorted(new_signatures)).encode()).hexdigest()
            
            if new_hash != self.signatures[file_path]:
                return False, "Public method signatures changed"
            
            return True, None
        except:
            return False, "Failed to parse new code"
    
    def is_protected(self, file_path: str) -> bool:
        """Check if file is protected interface"""
        normalized = file_path.replace('\\', '/')
        return any(p in normalized for p in self.PROTECTED_INTERFACES)
