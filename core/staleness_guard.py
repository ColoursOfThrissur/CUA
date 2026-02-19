"""
Staleness Guard - Detect file changes during multi-step operations
"""
import hashlib
from typing import Dict

class StalenessGuard:
    def __init__(self):
        self.file_hashes: Dict[str, str] = {}
    
    def snapshot(self, filepath: str, content: str) -> None:
        """Store hash of file content"""
        self.file_hashes[filepath] = hashlib.sha256(content.encode()).hexdigest()
    
    def is_stale(self, filepath: str, current_content: str) -> bool:
        """Check if file changed since snapshot"""
        if filepath not in self.file_hashes:
            return False
        current_hash = hashlib.sha256(current_content.encode()).hexdigest()
        return self.file_hashes[filepath] != current_hash
    
    def refresh(self, filepath: str, content: str) -> None:
        """Update snapshot after intentional change"""
        self.snapshot(filepath, content)
