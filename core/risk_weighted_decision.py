"""
Risk-weighted decision system - replace forbidden with thresholds
"""
from dataclasses import dataclass
from typing import Dict

@dataclass
class RiskWeightedDecision:
    risk_threshold: float = 0.7
    min_test_coverage: float = 0.8
    min_sandbox_passes: int = 3
    
    def evaluate_change(self, change_type: str, context: Dict) -> tuple[bool, str, float]:
        """Evaluate if change is acceptable based on risk"""
        risk_score = self._calculate_risk(change_type, context)
        
        if risk_score > self.risk_threshold:
            return False, f"Risk too high: {risk_score:.2f}", risk_score
        
        # Check test coverage
        coverage = context.get('test_coverage', 0.0)
        if coverage < self.min_test_coverage:
            return False, f"Coverage too low: {coverage:.2f}", risk_score
        
        # Check sandbox passes
        sandbox_passes = context.get('sandbox_passes', 0)
        if sandbox_passes < self.min_sandbox_passes:
            return False, f"Insufficient sandbox passes: {sandbox_passes}", risk_score
        
        return True, "Change acceptable", risk_score
    
    def _calculate_risk(self, change_type: str, context: Dict) -> float:
        """Calculate risk score for change"""
        base_risk = {
            "async_addition": 0.5,  # Not forbidden, just risky
            "caching_addition": 0.4,
            "refactoring": 0.3,
            "new_method": 0.2,
            "bug_fix": 0.1
        }.get(change_type, 0.5)
        
        # Adjust for context
        blast_radius = context.get('blast_radius', 0)
        if blast_radius > 5:
            base_risk += 0.2
        
        maturity = context.get('maturity', 'unknown')
        if maturity == 'experimental':
            base_risk += 0.1
        
        has_tests = context.get('has_tests', False)
        if not has_tests:
            base_risk += 0.3
        
        return min(base_risk, 1.0)
    
    def get_required_validations(self, risk_score: float) -> list:
        """Get validation requirements based on risk"""
        validations = ["syntax_check", "import_check"]
        
        if risk_score > 0.3:
            validations.extend(["unit_tests", "integration_tests"])
        
        if risk_score > 0.5:
            validations.extend(["coverage_check", "regression_tests"])
        
        if risk_score > 0.7:
            validations.extend(["manual_review", "rollback_plan"])
        
        return validations
