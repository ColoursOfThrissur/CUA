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
    gap_type: str = "missing_capability"
    suggested_action: str = "create_tool"
    selected_skill: str = None
    selected_category: str = None
    fallback_mode: str = None
    target_tool: str = None
    example_tasks: List[str] = None
    example_errors: List[str] = None
    # Resolution layer fields
    resolution_action: str = None   # reroute | mcp | api_wrap | create_tool
    resolution_target: str = None   # existing tool / MCP server / API name
    resolution_notes: List[str] = None
    resolution_attempted: bool = False

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
            if getattr(gap, "example_task", None):
                record.example_tasks = record.example_tasks or []
                if gap.example_task not in record.example_tasks:
                    record.example_tasks.append(gap.example_task)
                    record.example_tasks = record.example_tasks[-5:]
            if getattr(gap, "example_error", None):
                record.example_errors = record.example_errors or []
                if gap.example_error not in record.example_errors:
                    record.example_errors.append(gap.example_error)
                    record.example_errors = record.example_errors[-5:]
        else:
            # Create new
            self.gaps[gap.capability] = GapRecord(
                capability=gap.capability,
                first_seen=now,
                last_seen=now,
                occurrence_count=1,
                confidence_avg=gap.confidence,
                reasons=[gap.reason],
                suggested_library=gap.suggested_library,
                gap_type=getattr(gap, "gap_type", "missing_capability"),
                suggested_action=getattr(gap, "suggested_action", "create_tool"),
                selected_skill=getattr(gap, "selected_skill", None),
                selected_category=getattr(gap, "selected_category", None),
                fallback_mode=getattr(gap, "fallback_mode", None),
                target_tool=getattr(gap, "target_tool", None),
                example_tasks=[gap.example_task] if getattr(gap, "example_task", None) else [],
                example_errors=[gap.example_error] if getattr(gap, "example_error", None) else [],
            )
        if getattr(gap, "gap_type", None):
            self.gaps[gap.capability].gap_type = gap.gap_type
        if getattr(gap, "suggested_action", None):
            self.gaps[gap.capability].suggested_action = gap.suggested_action
        if getattr(gap, "selected_skill", None):
            self.gaps[gap.capability].selected_skill = gap.selected_skill
        if getattr(gap, "selected_category", None):
            self.gaps[gap.capability].selected_category = gap.selected_category
        if getattr(gap, "fallback_mode", None):
            self.gaps[gap.capability].fallback_mode = gap.fallback_mode
        if getattr(gap, "target_tool", None):
            self.gaps[gap.capability].target_tool = gap.target_tool
        
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

    def get_prioritized_gaps(self) -> List[GapRecord]:
        """Get actionable gaps ordered by impact. Gaps with cheaper resolutions sort lower."""
        prioritized = self.get_actionable_gaps()
        prioritized.sort(
            key=lambda gap: (
                gap.occurrence_count * (gap.confidence_avg or 0.0),
                # create_tool gaps rank highest (most urgent), cheaper resolutions rank lower
                1 if (gap.resolution_action or gap.suggested_action) == "create_tool" else 0,
            ),
            reverse=True,
        )
        return prioritized
    
    def mark_resolved(self, capability: str, action: str, target: str = None, notes: List[str] = None):
        """Mark a gap as resolved with the chosen resolution action."""
        if capability in self.gaps:
            record = self.gaps[capability]
            record.resolution_action = action
            record.resolution_target = target
            record.resolution_notes = notes or []
            record.resolution_attempted = True
            record.suggested_action = action  # keep suggested_action in sync
            self._save()

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
                    "suggested_library": gap.suggested_library,
                    "gap_type": gap.gap_type,
                    "suggested_action": gap.suggested_action,
                    "selected_skill": gap.selected_skill,
                    "selected_category": gap.selected_category,
                    "example_tasks": gap.example_tasks or [],
                    "example_errors": gap.example_errors or [],
                    "resolution_action": gap.resolution_action,
                    "resolution_target": gap.resolution_target,
                    "resolution_attempted": gap.resolution_attempted,
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
                # Tolerate old records missing new resolution fields
                valid_fields = {f.name for f in GapRecord.__dataclass_fields__.values()}
                self.gaps = {
                    k: GapRecord(**{fk: fv for fk, fv in v.items() if fk in valid_fields})
                    for k, v in data.items()
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
