"""
Audit Logger - Immutable audit trail for all updates
"""
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

@dataclass
class AuditEntry:
    entry_id: str
    timestamp: str
    update_id: str
    action: str
    risk_level: str
    files_changed: list
    approved_by: Optional[str]
    test_result: bool
    applied: bool
    previous_hash: str
    entry_hash: str

class AuditLogger:
    def __init__(self, audit_dir: str = "./audit"):
        self.audit_dir = Path(audit_dir)
        self.audit_dir.mkdir(exist_ok=True)
        self.audit_file = self.audit_dir / "audit.log"
        self.last_hash = self._get_last_hash()
    
    def log_update(self, update_id: str, action: str, risk_level: str,
                   files_changed: list, approved_by: Optional[str],
                   test_result: bool, applied: bool) -> str:
        """Log update with immutable hash chain"""
        
        entry_id = hashlib.sha256(f"{update_id}{datetime.now(timezone.utc).isoformat()}".encode()).hexdigest()[:16]
        
        entry = AuditEntry(
            entry_id=entry_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            update_id=update_id,
            action=action,
            risk_level=risk_level,
            files_changed=files_changed,
            approved_by=approved_by,
            test_result=test_result,
            applied=applied,
            previous_hash=self.last_hash,
            entry_hash=""
        )
        
        # Calculate entry hash
        entry_data = asdict(entry)
        entry_data.pop('entry_hash')
        entry_hash = hashlib.sha256(json.dumps(entry_data, sort_keys=True).encode()).hexdigest()
        entry.entry_hash = entry_hash
        
        # Append to log
        with open(self.audit_file, 'a') as f:
            f.write(json.dumps(asdict(entry)) + '\n')
        
        self.last_hash = entry_hash
        return entry_id
    
    def verify_integrity(self) -> bool:
        """Verify audit log integrity"""
        
        if not self.audit_file.exists():
            return True
        
        previous_hash = "genesis"
        
        with open(self.audit_file, 'r') as f:
            for line in f:
                entry = json.loads(line)
                
                if entry['previous_hash'] != previous_hash:
                    return False
                
                # Verify entry hash
                entry_copy = entry.copy()
                stored_hash = entry_copy.pop('entry_hash')
                calculated_hash = hashlib.sha256(json.dumps(entry_copy, sort_keys=True).encode()).hexdigest()
                
                if stored_hash != calculated_hash:
                    return False
                
                previous_hash = stored_hash
        
        return True
    
    def _get_last_hash(self) -> str:
        """Get hash of last entry"""
        
        if not self.audit_file.exists():
            return "genesis"
        
        with open(self.audit_file, 'r') as f:
            lines = f.readlines()
            if not lines:
                return "genesis"
            
            last_entry = json.loads(lines[-1])
            return last_entry['entry_hash']
    
    def get_recent(self, limit: int = 10) -> list:
        """Get recent audit entries"""
        
        if not self.audit_file.exists():
            return []
        
        with open(self.audit_file, 'r') as f:
            lines = f.readlines()
            return [json.loads(line) for line in lines[-limit:]]
