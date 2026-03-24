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
        self._tool_orchestrator = None  # injected after bootstrap
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
        tool_path = Path(evolution.get("tool_path") or evolution["proposal"]["analysis"]["tool_path"])
        tool_path.write_text(evolution["improved_code"])

        # Invalidate orchestrator services cache so next execution gets fresh ToolServices
        if self._tool_orchestrator:
            self._tool_orchestrator.invalidate_cache(tool_name)

        try:
            from core.skills import SkillUpdater

            SkillUpdater().apply_update_plans(evolution.get("skill_updates") or [])
        except Exception:
            pass
        
        # Update evolution log with health_after
        evolution_id = evolution.get("evolution_id")
        if evolution_id:
            try:
                from core.tool_evolution_logger import get_evolution_logger
                from core.tool_quality_analyzer import ToolQualityAnalyzer
                analyzer = ToolQualityAnalyzer()
                report = analyzer.analyze_tool(tool_name)
                health_after = report.health_score if report else None
                evo_logger = get_evolution_logger()
                # UPDATE the existing row rather than inserting a new one
                with __import__('sqlite3').connect(str(evo_logger.db_path)) as conn:
                    conn.execute(
                        "UPDATE evolution_runs SET status=?, step=?, health_after=? WHERE id=?",
                        ("approved", "complete", health_after, evolution_id)
                    )
                    conn.commit()
            except Exception as e:
                import logging as _log
                _log.getLogger(__name__).warning(f"Could not update health_after: {e}")
        
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
