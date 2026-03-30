"""
Pending Services Manager - Manages service approval queue
"""
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

class PendingServicesManager:
    def __init__(self, storage_path: str = "data/pending_services.json"):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_storage()
    
    def _ensure_storage(self):
        """Ensure storage file exists"""
        if not self.storage_path.exists():
            self.storage_path.write_text(json.dumps({"services": []}, indent=2))
    
    def _load(self) -> dict:
        """Load pending services"""
        try:
            return json.loads(self.storage_path.read_text())
        except:
            return {"services": []}
    
    def _save(self, data: dict):
        """Save pending services"""
        self.storage_path.write_text(json.dumps(data, indent=2))
    
    def add_pending_service(self, service_name: str, method_name: str, code: str, 
                           context: str = "", requested_by: str = "evolution") -> str:
        """Add a service to pending queue"""
        data = self._load()
        
        service_id = f"{service_name}_{method_name}_{datetime.now().timestamp()}"
        
        pending_service = {
            "id": service_id,
            "service_name": service_name,
            "method_name": method_name,
            "code": code,
            "context": context,
            "requested_by": requested_by,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "type": "method"
        }
        
        data["services"].append(pending_service)
        self._save(data)
        
        return service_id
    
    def add_pending_full_service(self, service_name: str, code: str, methods: list,
                                 context: str = "", requested_by: str = "evolution") -> str:
        """Add a full service class to pending queue"""
        data = self._load()
        
        service_id = f"{service_name}_full_{datetime.now().timestamp()}"
        
        pending_service = {
            "id": service_id,
            "service_name": service_name,
            "code": code,
            "methods": methods,
            "context": context,
            "requested_by": requested_by,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "type": "full_service"
        }
        
        data["services"].append(pending_service)
        self._save(data)
        
        return service_id
    
    def get_pending_services(self) -> List[dict]:
        """Get all pending services"""
        data = self._load()
        return [s for s in data["services"] if s["status"] == "pending"]
    
    def get_service(self, service_id: str) -> Optional[dict]:
        """Get a specific pending service"""
        data = self._load()
        for service in data["services"]:
            if service["id"] == service_id:
                return service
        return None
    
    def approve_service(self, service_id: str) -> bool:
        """Approve a pending service"""
        data = self._load()
        for service in data["services"]:
            if service["id"] == service_id:
                service["status"] = "approved"
                service["approved_at"] = datetime.now().isoformat()
                self._save(data)
                return True
        return False
    
    def reject_service(self, service_id: str, reason: str = "") -> bool:
        """Reject a pending service"""
        data = self._load()
        for service in data["services"]:
            if service["id"] == service_id:
                service["status"] = "rejected"
                service["rejected_at"] = datetime.now().isoformat()
                service["rejection_reason"] = reason
                self._save(data)
                return True
        return False
    
    def has_pending_service(self, service_name: str, method_name: str = None) -> bool:
        """Check if a service/method is already pending"""
        pending = self.get_pending_services()
        for service in pending:
            if service["service_name"] == service_name:
                if method_name is None or service.get("method_name") == method_name:
                    return True
        return False
    
    def get_evolutions_waiting_for_service(self, service_name: str, method_name: str = None) -> List[str]:
        """Get list of evolutions waiting for this service"""
        # This will be populated by the evolution system
        # For now, return empty list
        return []
