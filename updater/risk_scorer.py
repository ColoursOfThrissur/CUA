"""
Risk Scorer - Analyzes proposed changes and assigns risk levels
"""
from enum import Enum
from dataclasses import dataclass
from typing import List

class UpdateRiskLevel(Enum):
    VERY_LOW = "very_low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKED = "blocked"

@dataclass
class RiskScore:
    level: UpdateRiskLevel
    score: int
    reasons: List[str]
    critical_files: List[str]
    requires_approval: bool

class RiskScorer:
    BLOCKED_FILES = {
        "core/immutable_brain_stem.py",
        "core/session_permissions.py",
        "core/plan_schema.py"
    }
    
    # Also block any rename/move operations on critical files
    BLOCKED_PATTERNS = [
        "immutable_brain_stem",
        "session_permissions", 
        "plan_schema"
    ]
    
    HIGH_RISK_FILES = {
        "core/plan_validator.py",
        "core/state_machine.py",
        "core/secure_executor.py",
        "api/server.py"
    }
    
    MEDIUM_RISK_FILES = {
        "tools/enhanced_filesystem_tool.py",
        "tools/capability_registry.py",
        "planner/llm_client.py"
    }
    
    SAFE_PATTERNS = {"README", "CHANGELOG", ".md", "docs/", "examples/", "tests/"}
    
    def __init__(self):
        # PHASE 2A: Initialize dependency analyzer
        from core.dependency_analyzer import DependencyAnalyzer
        self.dependency_analyzer = DependencyAnalyzer()
        
        # PHASE 3C: Initialize failure learner
        from core.failure_learner import FailureLearner
        self.failure_learner = FailureLearner()
    
    def score_update(self, changed_files: List[str], diff_lines: int, change_type: str = "unknown") -> RiskScore:
        reasons = []
        critical_files = []
        score = 0.0  # Use float for normalization
        
        # Check for blocked files (including renames)
        for file in changed_files:
            normalized = file.replace("\\", "/")
            
            # Direct match
            if normalized in self.BLOCKED_FILES:
                return RiskScore(
                    level=UpdateRiskLevel.BLOCKED,
                    score=100,
                    reasons=[f"Blocked: Cannot modify {file}"],
                    critical_files=[file],
                    requires_approval=True
                )
            
            # Pattern match (catches renames)
            for pattern in self.BLOCKED_PATTERNS:
                if pattern in normalized:
                    return RiskScore(
                        level=UpdateRiskLevel.BLOCKED,
                        score=100,
                        reasons=[f"Blocked: File matches protected pattern '{pattern}'"],
                        critical_files=[file],
                        requires_approval=True
                    )
        
        # Calculate individual risk factors (normalized 0-1)
        blast_radius_score = 0.0
        core_module_score = 0.0
        failure_history_score = 0.0
        
        # PHASE 2A: Calculate blast radius for each file
        total_blast_radius = 0
        for file in changed_files:
            blast_radius = self.dependency_analyzer.calculate_blast_radius(file)
            total_blast_radius += blast_radius['total_affected']
            
            if blast_radius['is_core_module']:
                core_module_score = 1.0
                reasons.append(f"Core module: {file}")
                critical_files.append(file)
            elif blast_radius['total_affected'] > 10:
                blast_radius_score = max(blast_radius_score, 0.8)
                reasons.append(f"High blast radius: {file} affects {blast_radius['total_affected']} files")
            elif blast_radius['total_affected'] > 5:
                blast_radius_score = max(blast_radius_score, 0.5)
        
        # PHASE 3C: Check failure history
        for file in changed_files:
            risk_weight = self.failure_learner.get_risk_weight(file, change_type)
            if risk_weight > 0.5:
                failure_history_score = max(failure_history_score, risk_weight)
                reasons.append(f"High failure rate for {file} ({change_type})")
        
        # Other factors
        lines_score = min(1.0, diff_lines / 500)
        files_score = min(1.0, len(changed_files) / 10)
        
        # Weighted combination (normalized)
        weights = {
            'blast_radius': 0.25,
            'core_module': 0.25,
            'failure_history': 0.25,
            'lines': 0.125,
            'files': 0.125
        }
        
        base_score = (
            blast_radius_score * weights['blast_radius'] +
            core_module_score * weights['core_module'] +
            failure_history_score * weights['failure_history'] +
            lines_score * weights['lines'] +
            files_score * weights['files']
        )
        
        # Multiplicative escalation for combined high-risk factors
        if core_module_score > 0.5 and blast_radius_score > 0.5:
            base_score *= 1.5
            reasons.append("Multiplicative risk: core module + high blast radius")
        
        if failure_history_score > 0.5 and core_module_score > 0.5:
            base_score *= 1.3
            reasons.append("Multiplicative risk: failure history + core module")
        
        # Check for safe patterns
        all_safe = all(
            any(pattern in file for pattern in self.SAFE_PATTERNS)
            for file in changed_files
        )
        
        if all_safe:
            base_score *= 0.5
            reasons.append("Only documentation/tests changed")
        
        # Convert to 0-100 scale
        final_score = int(min(100, base_score * 100))
        
        if final_score >= 60:
            level = UpdateRiskLevel.HIGH
            requires_approval = True
        elif final_score >= 35:
            level = UpdateRiskLevel.MEDIUM
            requires_approval = True
        elif final_score >= 15:
            level = UpdateRiskLevel.LOW
            requires_approval = False
        else:
            level = UpdateRiskLevel.VERY_LOW
            requires_approval = False
        
        return RiskScore(
            level=level,
            score=final_score,
            reasons=reasons if reasons else ["Minimal changes"],
            critical_files=critical_files,
            requires_approval=requires_approval
        )
