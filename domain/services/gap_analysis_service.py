"""
Domain Service: Gap Analysis
Pure business logic for identifying capability gaps in the CUA system.
No infrastructure dependencies.
"""
from dataclasses import dataclass
from typing import List, Set, Optional
from enum import Enum

from domain.entities.gap import CapabilityGap


class GapConfidence(Enum):
    LOW = 0.5
    MEDIUM = 0.7
    HIGH = 0.9


@dataclass(frozen=True)
class SkillSnapshot:
    name: str
    description: str
    preferred_tools: List[str]
    capabilities_needed: List[str]


@dataclass(frozen=True)
class SystemSnapshot:
    skills: List[SkillSnapshot]
    existing_tools: List[str]
    covered_capabilities: Set[str]


class GapAnalysisService:
    """Pure domain service for gap analysis logic."""
    
    MIN_CONFIDENCE = 0.75
    MAX_GAPS_PER_ANALYSIS = 3
    MAX_REASON_WORDS = 8
    
    def should_analyze_gap(self, gap: CapabilityGap, covered_capabilities: Set[str]) -> bool:
        """Determine if a gap should be tracked."""
        if gap.confidence < self.MIN_CONFIDENCE:
            return False
        
        cap_key = gap.capability.lower().replace(":", "_")
        if cap_key in covered_capabilities:
            return False
        
        return True
    
    def is_gap_already_resolved(self, capability: str, resolved_gaps: dict) -> bool:
        """Check if gap was already resolved."""
        existing = resolved_gaps.get(capability)
        return existing is not None and existing.get("resolution_attempted", False)
    
    def normalize_capability_key(self, capability: str) -> str:
        """Normalize capability name for comparison."""
        return capability.lower().replace(":", "_").strip()
    
    def validate_gap_reason(self, reason: str) -> bool:
        """Validate gap reason meets constraints."""
        word_count = len(reason.split())
        return 0 < word_count <= self.MAX_REASON_WORDS
    
    def filter_valid_gaps(self, raw_gaps: List[dict], system: SystemSnapshot) -> List[dict]:
        """Filter and validate gaps from raw LLM output. Returns dict for entity creation."""
        valid_gaps = []
        
        for item in raw_gaps[:self.MAX_GAPS_PER_ANALYSIS]:
            cap = (item.get("capability") or "").strip()
            conf = float(item.get("confidence", 0.0))
            reason = (item.get("reason") or "").strip()
            suggested_name = (item.get("suggested_tool_name") or "").strip()
            
            if not cap or conf < self.MIN_CONFIDENCE:
                continue
            
            cap_key = self.normalize_capability_key(cap)
            if cap_key in system.covered_capabilities:
                continue
            
            gap_data = {
                "capability": cap,
                "confidence": min(conf, 0.95),
                "reason": reason,
                "target_tool": suggested_name if suggested_name else None
            }
            
            valid_gaps.append(gap_data)
        
        return valid_gaps
