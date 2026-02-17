"""
Update Gate - Enforces approval rules based on risk
"""
from enum import Enum
from dataclasses import dataclass
from typing import Optional
from datetime import datetime
from updater.risk_scorer import UpdateRiskLevel, RiskScore

class ApprovalStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    AUTO_APPROVED = "auto_approved"

@dataclass
class ApprovalRequest:
    update_id: str
    risk_score: RiskScore
    status: ApprovalStatus
    requested_at: datetime
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None

class UpdateGate:
    def __init__(self):
        self.pending_approvals = {}
    
    def check_gate(self, update_id: str, risk_score: RiskScore) -> ApprovalRequest:
        """Check if update can proceed"""
        
        # BLOCKED - never allow
        if risk_score.level == UpdateRiskLevel.BLOCKED:
            return ApprovalRequest(
                update_id=update_id,
                risk_score=risk_score,
                status=ApprovalStatus.REJECTED,
                requested_at=datetime.now()
            )
        
        # VERY_LOW and LOW - auto-approve
        if risk_score.level in [UpdateRiskLevel.VERY_LOW, UpdateRiskLevel.LOW]:
            return ApprovalRequest(
                update_id=update_id,
                risk_score=risk_score,
                status=ApprovalStatus.AUTO_APPROVED,
                requested_at=datetime.now(),
                approved_by="system",
                approved_at=datetime.now()
            )
        
        # MEDIUM and HIGH - require approval
        approval_req = ApprovalRequest(
            update_id=update_id,
            risk_score=risk_score,
            status=ApprovalStatus.PENDING,
            requested_at=datetime.now()
        )
        
        self.pending_approvals[update_id] = approval_req
        return approval_req
    
    def approve(self, update_id: str, approver: str) -> bool:
        """Approve pending update"""
        
        if update_id not in self.pending_approvals:
            return False
        
        approval = self.pending_approvals[update_id]
        approval.status = ApprovalStatus.APPROVED
        approval.approved_by = approver
        approval.approved_at = datetime.now()
        
        return True
    
    def reject(self, update_id: str) -> bool:
        """Reject pending update"""
        
        if update_id not in self.pending_approvals:
            return False
        
        approval = self.pending_approvals[update_id]
        approval.status = ApprovalStatus.REJECTED
        
        return True
    
    def get_pending(self):
        """Get all pending approvals"""
        return [
            approval for approval in self.pending_approvals.values()
            if approval.status == ApprovalStatus.PENDING
        ]
