"""
Domain Entity: Capability Gap
Represents a missing capability in the system.
"""
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class CapabilityGap:
    """Domain entity for capability gaps."""
    capability: str
    confidence: float
    reason: str
    domain: str = "system_analysis"
    gap_type: str = "llm_identified"
    suggested_action: str = "create_tool"
    target_tool: Optional[str] = None
    resolution_attempted: bool = False
    detected_at: datetime = field(default_factory=datetime.now)
    occurrences: int = 1
    
    def mark_resolution_attempted(self):
        """Mark that resolution was attempted."""
        self.resolution_attempted = True
    
    def increment_occurrences(self):
        """Increment occurrence count."""
        self.occurrences += 1
