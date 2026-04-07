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
            self.storage_path.write_text(json.dumps({"pending": [], "history": []}, indent=2))

    def _load(self) -> dict:
        """Load pending skills"""
        try:
            raw = json.loads(self.storage_path.read_text())
            return self._normalize_data(raw)
        except:
            return {"pending": [], "history": []}

    def _save(self, data: dict):
        """Save pending skills"""
        normalized = self._normalize_data(data)
        self.storage_path.write_text(json.dumps(normalized, indent=2))

    def _normalize_data(self, raw) -> dict:
        """Normalize legacy list/dict formats into the current shape."""
        if isinstance(raw, list):
            pending = []
            history = []
            for item in raw:
                if not isinstance(item, dict):
                    continue
                status = item.get("status", "pending")
                if status == "pending":
                    pending.append(item)
                else:
                    history.append(item)
            return {"pending": pending, "history": history}

        if isinstance(raw, dict):
            if "pending" in raw or "history" in raw:
                pending = raw.get("pending", [])
                history = raw.get("history", [])
                return {
                    "pending": pending if isinstance(pending, list) else [],
                    "history": history if isinstance(history, list) else [],
                }

            legacy_skills = raw.get("skills", [])
            if isinstance(legacy_skills, list):
                pending = []
                history = []
                for item in legacy_skills:
                    if not isinstance(item, dict):
                        continue
                    if item.get("status", "pending") == "pending":
                        pending.append(item)
                    else:
                        history.append(item)
                return {"pending": pending, "history": history}

        return {"pending": [], "history": []}
    
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
        
        data["pending"].append(pending_skill)
        self._save(data)
        
        return skill_id

    def get_pending_skills(self) -> List[dict]:
        """Get all pending skills"""
        data = self._load()
        return list(data["pending"])

    def get_history(self) -> List[dict]:
        """Get approved/rejected skill history."""
        data = self._load()
        return list(data["history"])

    def get_skill(self, skill_id: str) -> Optional[dict]:
        """Get a specific pending skill"""
        data = self._load()
        for skill in data["pending"]:
            if skill["id"] == skill_id:
                return skill
        for skill in data["history"]:
            if skill["id"] == skill_id:
                return skill
        return None

    def approve_skill(self, skill_id: str) -> bool:
        """Approve a pending skill"""
        data = self._load()
        for index, skill in enumerate(data["pending"]):
            if skill["id"] == skill_id:
                approved_skill = dict(skill)
                approved_skill["status"] = "approved"
                approved_skill["approved_at"] = datetime.now().isoformat()
                del data["pending"][index]
                data["history"].append(approved_skill)
                self._save(data)
                return True
        return False

    def reject_skill(self, skill_id: str, reason: str = "") -> bool:
        """Reject a pending skill"""
        data = self._load()
        for index, skill in enumerate(data["pending"]):
            if skill["id"] == skill_id:
                rejected_skill = dict(skill)
                rejected_skill["status"] = "rejected"
                rejected_skill["rejected_at"] = datetime.now().isoformat()
                rejected_skill["rejection_reason"] = reason
                del data["pending"][index]
                data["history"].append(rejected_skill)
                self._save(data)
                return True
        return False

    def has_pending_skill(self, skill_name: str) -> bool:
        """Check if a skill is already pending"""
        pending = self.get_pending_skills()
        return any(s["skill_name"] == skill_name for s in pending)
