"""
Idempotency Checker - Prevent duplicate changes
"""
import hashlib
import json
from pathlib import Path
from typing import Optional

class IdempotencyChecker:
    def __init__(self, db_path: str = "./data/applied_changes.json"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._load()
    
    def _load(self):
        """Load applied changes database"""
        if self.db_path.exists():
            try:
                self.applied = json.loads(self.db_path.read_text())
            except:
                self.applied = {}
        else:
            self.applied = {}
    
    def _save(self):
        """Save applied changes database"""
        self.db_path.write_text(json.dumps(self.applied, indent=2))
    
    def get_change_hash(self, file_path: str, description: str) -> str:
        """Generate hash for change"""
        key = f"{file_path}::{description.lower()}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]
    
    def is_duplicate(self, file_path: str, description: str) -> tuple[bool, Optional[str]]:
        """Check if change already applied"""
        change_hash = self.get_change_hash(file_path, description)
        
        if change_hash in self.applied:
            prev = self.applied[change_hash]
            return True, f"Already applied on {prev['timestamp']}"
        
        return False, None
    
    def record_change(self, file_path: str, description: str, update_id: str):
        """Record applied change"""
        from datetime import datetime
        change_hash = self.get_change_hash(file_path, description)
        
        self.applied[change_hash] = {
            "file": file_path,
            "description": description,
            "update_id": update_id,
            "timestamp": datetime.now().isoformat()
        }
        self._save()
