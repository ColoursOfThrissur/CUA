"""Filesystem service wrapper for tools"""
from pathlib import Path
from typing import List

class FileSystemService:
    """Provides filesystem capabilities to tools"""
    
    def __init__(self, allowed_roots: List[str]):
        self.allowed_roots = allowed_roots
    
    def read(self, path: str) -> str:
        """Read file content"""
        if not self._validate_path(path):
            raise ValueError(f"Path outside allowed roots: {path}")
        return Path(path).read_text(encoding='utf-8')
    
    def write(self, path: str, content: str) -> str:
        """Write file content"""
        if not self._validate_path(path):
            raise ValueError(f"Path outside allowed roots: {path}")
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding='utf-8')
        return f"Written to {path}"
    
    def list(self, path: str = ".") -> List[str]:
        """List directory contents"""
        if not self._validate_path(path):
            raise ValueError(f"Path outside allowed roots: {path}")
        return [item.name for item in Path(path).iterdir()]
    
    def _validate_path(self, path: str) -> bool:
        """Validate path is within allowed roots"""
        import os
        abs_path = os.path.abspath(path)
        for root in self.allowed_roots:
            abs_root = os.path.abspath(root)
            if abs_path.startswith(abs_root):
                return True
        return False
