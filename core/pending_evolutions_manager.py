"""Pending evolutions manager - like pending tools but for improvements."""
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime


class PendingEvolutionsManager:
    """Manages pending tool evolutions awaiting approval."""
    
    def __init__(self, storage_path: str = "data/pending_evolutions.json"):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_storage()
    
    def _ensure_storage(self):
        """Ensure storage file exists."""
        if not self.storage_path.exists():
            self.storage_path.write_text(json.dumps({}))
    
    def add_pending_evolution(self, tool_name: str, evolution_data: Dict[str, Any]):
        """Add evolution to pending list."""
        evolutions = self._load()
        
        evolution_data["created_at"] = datetime.now().isoformat()
        evolution_data["status"] = "pending"
        
        evolutions[tool_name] = evolution_data
        
        self._save(evolutions)
    
    def get_pending_evolution(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Get specific pending evolution."""
        evolutions = self._load()
        return evolutions.get(tool_name)
    
    def get_all_pending(self) -> List[Dict[str, Any]]:
        """Get all pending evolutions."""
        evolutions = self._load()
        return [
            {"tool_name": name, **data}
            for name, data in evolutions.items()
            if data.get("status") == "pending"
        ]
    
    def approve_evolution(self, tool_name: str) -> bool:
        """Approve evolution and apply changes."""
        evolutions = self._load()
        evolution = evolutions.get(tool_name)
        
        if not evolution:
            return False
        
        # Apply changes to actual file
        tool_path = Path(evolution["proposal"]["analysis"]["tool_path"])
        tool_path.write_text(evolution["improved_code"])
        
        # Update status
        evolution["status"] = "approved"
        evolution["approved_at"] = datetime.now().isoformat()
        
        self._save(evolutions)
        
        return True
    
    def reject_evolution(self, tool_name: str) -> bool:
        """Reject evolution."""
        evolutions = self._load()
        
        if tool_name not in evolutions:
            return False
        
        evolution = evolutions[tool_name]
        evolution["status"] = "rejected"
        evolution["rejected_at"] = datetime.now().isoformat()
        
        self._save(evolutions)
        
        return True
    
    def _load(self) -> Dict:
        """Load evolutions from storage."""
        try:
            return json.loads(self.storage_path.read_text())
        except:
            return {}
    
    def _save(self, evolutions: Dict):
        """Save evolutions to storage."""
        self.storage_path.write_text(json.dumps(evolutions, indent=2))
