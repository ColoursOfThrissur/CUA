"""
Proposal type system for autonomous evolution
"""
from enum import Enum
from dataclasses import dataclass
from typing import List, Optional

class ProposalType(Enum):
    MICRO_PATCH = "micro_patch"  # Single method improvement
    STRUCTURAL_UPGRADE = "structural_upgrade"  # Refactoring within file
    TOOL_EXTENSION = "tool_extension"  # Add capability to existing tool
    NEW_TOOL = "new_tool"  # Create new tool

@dataclass
class EvolutionProposal:
    proposal_type: ProposalType
    target_file: str
    description: str
    justification: str
    estimated_risk: float  # 0.0-1.0
    requires_expansion_mode: bool
    methods_affected: List[str]
    
    def is_permitted(self, growth_budget: 'GrowthBudget') -> tuple[bool, str]:
        """Controller decides if proposal is permitted"""
        if self.proposal_type == ProposalType.NEW_TOOL:
            if not growth_budget.can_create_tool():
                return False, "Growth budget exhausted for new tools"
        
        if self.proposal_type == ProposalType.STRUCTURAL_UPGRADE:
            if not growth_budget.can_structural_change():
                return False, "Growth budget exhausted for structural changes"
        
        if self.estimated_risk > 0.7:
            return False, f"Risk too high: {self.estimated_risk}"
        
        return True, "Proposal permitted"
