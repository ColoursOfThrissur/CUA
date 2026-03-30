"""
Pending Skills Manager - Manages skill approval queue
"""
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

class PendingSkillsManager:
    def __init__(self, storage_path: str = "data/pending_skills.json"):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_storage()
    
    def _ensure_storage(self):
        """Ensure storage file exists"""
        if not self.storage_path.exists():
            self.storage_path.write_text(json.dumps({"skills": []}, indent=2))
    
    def _load(self) -> dict:
        """Load pending skills"""
        try:
            return json.loads(self.storage_path.read_text())
        except:
            return {"skills": []}
    
    def _save(self, data: dict):
        """Save pending skills"""
        self.storage_path.write_text(json.dumps(data, indent=2))
    
    def add_pending_skill(self, skill_name: str, skill_definition: dict, 
                         instructions: str = "", context: str = "", 
                         requested_by: str = "gap_detection") -> str:
        """Add a skill to pending queue"""
        data = self._load()
        
        skill_id = f"{skill_name}_{datetime.now().timestamp()}"
        
        pending_skill = {
            "id": skill_id,
            "skill_name": skill_name,
            "skill_definition": skill_definition,
            "instructions": instructions,
            "context": context,
            "requested_by": requested_by,
            "status": "pending",
            "created_at": datetime.now().isoformat()
        }
        
        data["skills"].append(pending_skill)
        self._save(data)
        
        return skill_id
    
    def get_pending_skills(self) -> List[dict]:
        """Get all pending skills"""
        data = self._load()
        return [s for s in data["skills"] if s["status"] == "pending"]
    
    def get_skill(self, skill_id: str) -> Optional[dict]:
        """Get a specific pending skill"""
        data = self._load()
        for skill in data["skills"]:
            if skill["id"] == skill_id:
                return skill
        return None
    
    def approve_skill(self, skill_id: str) -> bool:
        """Approve a pending skill"""
        data = self._load()
        for skill in data["skills"]:
            if skill["id"] == skill_id:
                skill["status"] = "approved"
                skill["approved_at"] = datetime.now().isoformat()
                self._save(data)
                return True
        return False
    
    def reject_skill(self, skill_id: str, reason: str = "") -> bool:
        """Reject a pending skill"""
        data = self._load()
        for skill in data["skills"]:
            if skill["id"] == skill_id:
                skill["status"] = "rejected"
                skill["rejected_at"] = datetime.now().isoformat()
                skill["rejection_reason"] = reason
                self._save(data)
                return True
        return False
    
    def has_pending_skill(self, skill_name: str) -> bool:
        """Check if a skill is already pending"""
        pending = self.get_pending_skills()
        return any(s["skill_name"] == skill_name for s in pending)
