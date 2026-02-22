"""Evolution Queue Manager - Manages prioritized queue of tools needing evolution."""
import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict

@dataclass
class QueuedEvolution:
    """Represents a tool queued for evolution."""
    tool_name: str
    urgency_score: float
    impact_score: float
    feasibility_score: float
    timing_score: float
    reason: str
    metadata: Dict[str, Any] = None
    queued_at: float = None
    status: str = "queued"
    
    def __post_init__(self):
        if self.queued_at is None:
            self.queued_at = time.time()
        if self.metadata is None:
            self.metadata = {}
    
    @property
    def priority_score(self) -> float:
        """Calculate priority score."""
        return (
            self.urgency_score * 0.35 +
            self.impact_score * 0.30 +
            self.feasibility_score * 0.20 +
            self.timing_score * 0.15
        )

class EvolutionQueue:
    """Manages evolution queue with prioritization."""
    
    def __init__(self, storage_path: str = "data/evolution_queue.json"):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(exist_ok=True)
        self.queue: List[QueuedEvolution] = []
        self.in_progress: Optional[str] = None
        self._load()
    
    def add(self, evolution: 'QueuedEvolution'):
        """Add evolution to queue."""
        if not self.is_queued(evolution.tool_name):
            self.queue.append(evolution)
            self._sort_queue()
            self._save()
    
    def get_next(self) -> Optional['QueuedEvolution']:
        """Get next evolution from queue."""
        queued = [e for e in self.queue if e.status == "queued"]
        return queued[0] if queued else None
    
    def is_queued(self, tool_name: str) -> bool:
        """Check if tool is queued."""
        return any(e.tool_name == tool_name for e in self.queue)
    
    def mark_in_progress(self, tool_name: str):
        """Mark tool as in progress."""
        for e in self.queue:
            if e.tool_name == tool_name:
                e.status = "in_progress"
                self.in_progress = tool_name
                self._save()
                break
    
    def mark_completed(self, tool_name: str):
        """Mark evolution complete and remove."""
        self.queue = [e for e in self.queue if e.tool_name != tool_name]
        if self.in_progress == tool_name:
            self.in_progress = None
        self._save()
    
    def mark_failed(self, tool_name: str, error: str):
        """Mark evolution failed and remove."""
        self.queue = [e for e in self.queue if e.tool_name != tool_name]
        if self.in_progress == tool_name:
            self.in_progress = None
        self._save()
    
    def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status."""
        queued = [e for e in self.queue if e.status == "queued"]
        
        return {
            "total_queued": len(queued),
            "in_progress": self.in_progress,
            "queue": [asdict(e) for e in queued[:10]]  # Top 10
        }
    
    def clear_queue(self):
        """Clear entire queue."""
        self.queue = []
        self.in_progress = None
        self._save()
    
    def _calculate_priority(self, scores: Dict[str, float]) -> float:
        """Calculate overall priority score."""
        return (
            scores.get('urgency', 0) * 0.35 +
            scores.get('impact', 0) * 0.30 +
            scores.get('feasibility', 0) * 0.20 +
            scores.get('timing', 0) * 0.15
        )
    
    def _sort_queue(self):
        """Sort queue by priority (highest first)."""
        self.queue.sort(key=lambda e: e.priority_score, reverse=True)
    
    def _load(self):
        """Load queue from storage."""
        if self.storage_path.exists():
            try:
                data = json.loads(self.storage_path.read_text())
                self.queue = [QueuedEvolution(**e) for e in data.get('queue', [])]
                self.in_progress = data.get('in_progress')
            except Exception as e:
                print(f"Failed to load evolution queue: {e}")
                self.queue = []
                self.in_progress = None
    
    def _save(self):
        """Save queue to storage."""
        data = {
            'queue': [asdict(e) for e in self.queue],
            'in_progress': self.in_progress,
            'last_updated': time.time()
        }
        self.storage_path.write_text(json.dumps(data, indent=2))

_queue = None

def get_evolution_queue() -> EvolutionQueue:
    """Get singleton queue."""
    global _queue
    if _queue is None:
        _queue = EvolutionQueue()
    return _queue
