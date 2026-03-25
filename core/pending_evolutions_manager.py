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
                from core.cua_db import get_conn as _get_conn
                report = ToolQualityAnalyzer().analyze_tool(tool_name)
                # Use measured score if available; fall back to health_before as baseline
                # so the column is never NULL and health trajectory is always visible.
                health_after = (report.health_score if report else None) or evolution.get("health_before")
                with _get_conn() as conn:
                    conn.execute(
                        "UPDATE evolution_runs SET status=?, step=?, health_after=? WHERE id=?",
                        ("approved", "complete", health_after, evolution_id)
                    )
            except Exception as e:
                import logging as _log
                _log.getLogger(__name__).warning(f"Could not update health_after: {e}")
        
        # Remove from pending list
        del evolutions[tool_name]
        
        self._save(evolutions)

        # Trim old backups — keep only the 3 most recent per tool
        try:
            self._trim_backups(tool_name)
        except Exception:
            pass
        
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
    
    def _trim_backups(self, tool_name: str, keep: int = 3):
        """Keep only the most recent `keep` backups for this tool."""
        backup_dir = Path("data/tool_backups")
        if not backup_dir.exists():
            return
        files = sorted(
            backup_dir.glob(f"{tool_name}_*.bak"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        for old in files[keep:]:
            old.unlink(missing_ok=True)

    def _load(self) -> Dict:
        """Load evolutions from storage."""
        try:
            return json.loads(self.storage_path.read_text())
        except:
            return {}
    
    def _save(self, evolutions: Dict):
        """Save evolutions to storage."""
        self.storage_path.write_text(json.dumps(evolutions, indent=2))
