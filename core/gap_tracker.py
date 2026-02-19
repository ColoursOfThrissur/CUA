"""
Gap Tracker - Tracks persistence of capability gaps over time
"""
import json
from pathlib import Path
from typing import Dict, List
from datetime import datetime
from dataclasses import dataclass, asdict

@dataclass
class GapRecord:
    capability: str
    first_seen: str
    last_seen: str
    occurrence_count: int
    confidence_avg: float
    reasons: List[str]
    suggested_library: str = None

class GapTracker:
    def __init__(self, data_file: str = "data/capability_gaps.json"):
        self.data_file = Path(data_file)
        self.gaps: Dict[str, GapRecord] = {}
        self._load()
    
    def record_gap(self, gap: 'CapabilityGap'):
        """Record a detected gap"""
        now = datetime.now().isoformat()
        
        if gap.capability in self.gaps:
            # Update existing
            record = self.gaps[gap.capability]
            record.last_seen = now
            record.occurrence_count += 1
            # Update rolling average confidence
            record.confidence_avg = (record.confidence_avg * (record.occurrence_count - 1) + gap.confidence) / record.occurrence_count
            if gap.reason not in record.reasons:
                record.reasons.append(gap.reason)
        else:
            # Create new
            self.gaps[gap.capability] = GapRecord(
                capability=gap.capability,
                first_seen=now,
                last_seen=now,
                occurrence_count=1,
                confidence_avg=gap.confidence,
                reasons=[gap.reason],
                suggested_library=gap.suggested_library
            )
        
        self._save()
    
    def get_persistent_gaps(self, min_occurrences: int = 3) -> List[GapRecord]:
        """Get gaps that have occurred multiple times"""
        return [
            gap for gap in self.gaps.values()
            if gap.occurrence_count >= min_occurrences
        ]
    
    def get_high_confidence_gaps(self, min_confidence: float = 0.7) -> List[GapRecord]:
        """Get gaps with high confidence scores"""
        return [
            gap for gap in self.gaps.values()
            if gap.confidence_avg >= min_confidence
        ]
    
    def get_actionable_gaps(self) -> List[GapRecord]:
        """Get gaps that are both persistent and high confidence"""
        return [
            gap for gap in self.gaps.values()
            if gap.occurrence_count >= 3 and gap.confidence_avg >= 0.7
        ]
    
    def clear_gap(self, capability: str):
        """Clear a gap (e.g., after tool is created)"""
        if capability in self.gaps:
            del self.gaps[capability]
            self._save()
    
    def get_summary(self) -> Dict:
        """Get summary statistics"""
        return {
            "total_gaps": len(self.gaps),
            "persistent_gaps": len(self.get_persistent_gaps()),
            "high_confidence_gaps": len(self.get_high_confidence_gaps()),
            "actionable_gaps": len(self.get_actionable_gaps()),
            "gaps": [
                {
                    "capability": gap.capability,
                    "occurrences": gap.occurrence_count,
                    "confidence": round(gap.confidence_avg, 2),
                    "suggested_library": gap.suggested_library
                }
                for gap in sorted(self.gaps.values(), key=lambda x: x.occurrence_count, reverse=True)
            ]
        }
    
    def _load(self):
        """Load gaps from disk"""
        if self.data_file.exists():
            try:
                with open(self.data_file) as f:
                    data = json.load(f)
                    self.gaps = {
                        k: GapRecord(**v) for k, v in data.items()
                    }
            except Exception:
                self.gaps = {}
    
    def _save(self):
        """Save gaps to disk"""
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.data_file, 'w') as f:
            json.dump(
                {k: asdict(v) for k, v in self.gaps.items()},
                f,
                indent=2
            )
