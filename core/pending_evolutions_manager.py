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
        
        # Update evolution log with health_after
        evolution_id = evolution.get("evolution_id")
        if evolution_id:
            from core.tool_evolution_logger import get_evolution_logger
            from core.tool_quality_analyzer import ToolQualityAnalyzer
            
            # Calculate new health score
            try:
                analyzer = ToolQualityAnalyzer()
                report = analyzer.analyze_tool(tool_name)
                health_after = report.health_score if report else None
                
                # Log final status with health_after
                evo_logger = get_evolution_logger()
                evo_logger.log_run(
                    tool_name=tool_name,
                    user_prompt=None,
                    status="approved",
                    step="complete",
                    health_after=health_after
                )
            except Exception as e:
                print(f"Warning: Could not update health_after: {e}")
        
        # Remove from pending list
        del evolutions[tool_name]
        
        self._save(evolutions)
        
        return True
    
    def reject_evolution(self, tool_name: str) -> bool:
        """Reject evolution."""
        evolutions = self._load()
        
        if tool_name not in evolutions:
            return False
        
        # Remove from pending list
        del evolutions[tool_name]
        
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
