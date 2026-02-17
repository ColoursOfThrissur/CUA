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
    
    def score_update(self, changed_files: List[str], diff_lines: int) -> RiskScore:
        reasons = []
        critical_files = []
        score = 0
        
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
        
        high_risk_found = []
        for file in changed_files:
            normalized = file.replace("\\", "/")
            if normalized in self.HIGH_RISK_FILES:
                high_risk_found.append(file)
                score += 30
        
        if high_risk_found:
            reasons.append(f"High-risk files: {', '.join(high_risk_found)}")
            critical_files.extend(high_risk_found)
        
        medium_risk_found = []
        for file in changed_files:
            normalized = file.replace("\\", "/")
            if normalized in self.MEDIUM_RISK_FILES:
                medium_risk_found.append(file)
                score += 15
        
        if medium_risk_found:
            reasons.append(f"Medium-risk files: {', '.join(medium_risk_found)}")
        
        if diff_lines > 500:
            score += 25
            reasons.append(f"Large diff: {diff_lines} lines")
        elif diff_lines > 200:
            score += 15
            reasons.append(f"Moderate diff: {diff_lines} lines")
        elif diff_lines > 50:
            score += 5
        
        if len(changed_files) > 10:
            score += 20
            reasons.append(f"Many files changed: {len(changed_files)}")
        elif len(changed_files) > 5:
            score += 10
        
        all_safe = all(
            any(pattern in file for pattern in self.SAFE_PATTERNS)
            for file in changed_files
        )
        
        if all_safe:
            score = max(0, score - 20)
            reasons.append("Only documentation/tests changed")
        
        if score >= 60:
            level = UpdateRiskLevel.HIGH
            requires_approval = True
        elif score >= 35:
            level = UpdateRiskLevel.MEDIUM
            requires_approval = True
        elif score >= 15:
            level = UpdateRiskLevel.LOW
            requires_approval = False
        else:
            level = UpdateRiskLevel.VERY_LOW
            requires_approval = False
        
        return RiskScore(
            level=level,
            score=score,
            reasons=reasons if reasons else ["Minimal changes"],
            critical_files=critical_files,
            requires_approval=requires_approval
        )
