"""
Growth budget system for rate-limited expansion
"""
from dataclasses import dataclass
from typing import Dict
import json
from pathlib import Path

@dataclass
class GrowthBudget:
    max_new_tools_per_20_cycles: int = 1
    max_structural_changes_per_10_cycles: int = 3
    current_cycle: int = 0
    new_tools_created: int = 0
    structural_changes_made: int = 0
    history_file: str = "data/growth_history.json"
    
    def __post_init__(self):
        self._load_history()
    
    def can_create_tool(self) -> bool:
        """Check if new tool creation is within budget"""
        cycles_since_reset = self.current_cycle % 20
        if cycles_since_reset == 0:
            self.new_tools_created = 0
        return self.new_tools_created < self.max_new_tools_per_20_cycles
    
    def can_structural_change(self) -> bool:
        """Check if structural change is within budget"""
        cycles_since_reset = self.current_cycle % 10
        if cycles_since_reset == 0:
            self.structural_changes_made = 0
        return self.structural_changes_made < self.max_structural_changes_per_10_cycles
    
    def record_tool_creation(self):
        """Record new tool creation"""
        self.new_tools_created += 1
        self._save_history()
    
    def record_structural_change(self):
        """Record structural change"""
        self.structural_changes_made += 1
        self._save_history()
    
    def increment_cycle(self):
        """Move to next cycle"""
        self.current_cycle += 1
        self._save_history()
    
    def _load_history(self):
        """Load growth history from disk"""
        path = Path(self.history_file)
        if path.exists():
            with open(path) as f:
                data = json.load(f)
                self.current_cycle = data.get("current_cycle", 0)
                self.new_tools_created = data.get("new_tools_created", 0)
                self.structural_changes_made = data.get("structural_changes_made", 0)
    
    def _save_history(self):
        """Save growth history to disk"""
        path = Path(self.history_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump({
                "current_cycle": self.current_cycle,
                "new_tools_created": self.new_tools_created,
                "structural_changes_made": self.structural_changes_made
            }, f, indent=2)
