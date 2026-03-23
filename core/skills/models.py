from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class SkillDefinition:
    name: str
    category: str
    description: str
    trigger_examples: List[str]
    preferred_tools: List[str]
    required_tools: List[str]
    preferred_connectors: List[str]
    input_types: List[str]
    output_types: List[str]
    verification_mode: str
    risk_level: str
    ui_renderer: str
    fallback_strategy: str
    skill_dir: str
    instructions_path: str
    metadata: dict = field(default_factory=dict)
    
    @property
    def expected_input_types(self) -> List[str]:
        """Alias for input_types (used by execution context)."""
        return self.input_types
    
    @property
    def expected_output_types(self) -> List[str]:
        """Alias for output_types (used by execution context)."""
        return self.output_types


@dataclass
class SkillSelection:
    matched: bool
    skill_name: Optional[str] = None
    category: Optional[str] = None
    confidence: float = 0.0
    reason: str = ""
    fallback_mode: str = "direct_tool_routing"
    candidate_skills: List[str] = field(default_factory=list)


@dataclass
class SkillPlanningContext:
    skill_name: str
    category: str
    instructions_summary: str
    preferred_tools: List[str]
    required_tools: List[str]
    verification_mode: str
    output_types: List[str]
    ui_renderer: str
    skill_constraints: List[str] = field(default_factory=list)
