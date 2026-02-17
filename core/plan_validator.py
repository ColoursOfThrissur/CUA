from typing import List, Dict, Any
from dataclasses import dataclass
from .immutable_brain_stem import BrainStem, ValidationResult, RiskLevel

@dataclass
class PlanValidationResult:
    is_approved: bool
    risk_assessment: RiskLevel
    failed_steps: List[int]
    reasons: List[str]
    total_steps: int

class PlanValidator:
    """Validates execution plans using brain stem safety rules."""
    
    def __init__(self):
        from core.config_manager import get_config
        config = get_config()
        self.max_steps = config.security.max_plan_steps
        self.max_risk_level = RiskLevel.MEDIUM
    
    def validate_plan(self, plan) -> PlanValidationResult:
        """Validate entire execution plan."""
        failed_steps = []
        reasons = []
        # Track the maximum observed risk using explicit ordering
        risk_order = [RiskLevel.SAFE, RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.BLOCKED]
        max_risk = RiskLevel.SAFE
        
        # Check plan size
        if len(plan.steps) > self.max_steps:
            return PlanValidationResult(
                is_approved=False,
                risk_assessment=RiskLevel.HIGH,
                failed_steps=[],
                reasons=[f"Plan too large: {len(plan.steps)} > {self.max_steps}"],
                total_steps=len(plan.steps)
            )
        
        # Validate each step
        for i, step in enumerate(plan.steps):
            result = BrainStem.validate_plan_step(
                step.tool, 
                step.operation, 
                step.parameters
            )
            
            if not result.is_valid:
                failed_steps.append(i)
                reasons.append(f"Step {i+1}: {result.reason}")
            
            # Track maximum risk level using the defined ordering
            try:
                if risk_order.index(result.risk_level) > risk_order.index(max_risk):
                    max_risk = result.risk_level
            except ValueError:
                # If an unexpected RiskLevel is returned, escalate to HIGH
                max_risk = RiskLevel.HIGH
        
        # Check if risk level is acceptable
        is_approved = (
            len(failed_steps) == 0 and 
            max_risk in [RiskLevel.SAFE, RiskLevel.LOW, RiskLevel.MEDIUM]
        )
        
        return PlanValidationResult(
            is_approved=is_approved,
            risk_assessment=max_risk,
            failed_steps=failed_steps,
            reasons=reasons,
            total_steps=len(plan.steps)
        )
    
    def validate_single_step(self, tool: str, operation: str, parameters: Dict[str, Any]) -> ValidationResult:
        """Validate single step for real-time checking."""
        return BrainStem.validate_plan_step(tool, operation, parameters)