"""
Update Orchestrator - Coordinates the entire update pipeline
"""
from uuid import uuid4
from typing import Tuple, Optional
from dataclasses import dataclass
from updater.risk_scorer import RiskScorer, RiskScore
from updater.sandbox_runner import SandboxRunner
from updater.update_gate import UpdateGate, ApprovalStatus
from updater.audit_logger import AuditLogger
from updater.atomic_applier import AtomicApplier

@dataclass
class UpdateResult:
    success: bool
    update_id: str
    risk_score: RiskScore
    approval_status: str
    test_passed: bool
    applied: bool
    error: Optional[str] = None
    audit_entry_id: Optional[str] = None

class UpdateOrchestrator:
    def __init__(self, repo_path: str):
        self.repo_path = repo_path
        self.risk_scorer = RiskScorer()
        self.sandbox_runner = SandboxRunner(repo_path)
        self.update_gate = UpdateGate()
        self.audit_logger = AuditLogger()
        self.atomic_applier = AtomicApplier(repo_path)
        
        # Idempotency checker
        from shared.utils.idempotency_checker import IdempotencyChecker
        self.idempotency_checker = IdempotencyChecker()
    
    def propose_update(self, patch_content: str, changed_files: list, diff_lines: int, description: str = "") -> UpdateResult:
        """Process update proposal through full pipeline with idempotency check"""
        
        update_id = str(uuid4())[:8]
        
        # Step 0: Check idempotency
        if changed_files and description:
            is_dup, reason = self.idempotency_checker.is_duplicate(changed_files[0], description)
            if is_dup:
                return UpdateResult(
                    success=False,
                    update_id=update_id,
                    risk_score=None,
                    approval_status="duplicate",
                    test_passed=False,
                    applied=False,
                    error=f"Duplicate change: {reason}"
                )
        
        # Step 1: Score risk
        risk_score = self.risk_scorer.score_update(changed_files, diff_lines)
        
        # Step 2: Check gate
        approval_req = self.update_gate.check_gate(update_id, risk_score)
        
        # If blocked, stop here
        if approval_req.status == ApprovalStatus.REJECTED:
            audit_id = self.audit_logger.log_update(
                update_id=update_id,
                action="proposed",
                risk_level=risk_score.level.value,
                files_changed=changed_files,
                approved_by=None,
                test_result=False,
                applied=False
            )
            
            return UpdateResult(
                success=False,
                update_id=update_id,
                risk_score=risk_score,
                approval_status=approval_req.status.value,
                test_passed=False,
                applied=False,
                error="Update blocked - cannot modify critical files",
                audit_entry_id=audit_id
            )
        
        # If requires approval, wait
        if approval_req.status == ApprovalStatus.PENDING:
            audit_id = self.audit_logger.log_update(
                update_id=update_id,
                action="pending_approval",
                risk_level=risk_score.level.value,
                files_changed=changed_files,
                approved_by=None,
                test_result=False,
                applied=False
            )
            
            return UpdateResult(
                success=False,
                update_id=update_id,
                risk_score=risk_score,
                approval_status=approval_req.status.value,
                test_passed=False,
                applied=False,
                error="Awaiting human approval",
                audit_entry_id=audit_id
            )
        
        # Step 3: Run in sandbox
        sandbox_result = self.sandbox_runner.run_in_sandbox(patch_content)
        
        if not sandbox_result.success:
            audit_id = self.audit_logger.log_update(
                update_id=update_id,
                action="tested",
                risk_level=risk_score.level.value,
                files_changed=changed_files,
                approved_by=approval_req.approved_by,
                test_result=False,
                applied=False
            )
            
            return UpdateResult(
                success=False,
                update_id=update_id,
                risk_score=risk_score,
                approval_status=approval_req.status.value,
                test_passed=False,
                applied=False,
                error=f"Tests failed: {sandbox_result.error}",
                audit_entry_id=audit_id
            )
        
        # Step 4: Apply atomically
        apply_success, apply_error = self.atomic_applier.apply_update(patch_content, update_id)
        
        # Record change if successful
        if apply_success and changed_files and description:
            self.idempotency_checker.record_change(changed_files[0], description, update_id)
        
        # Step 5: Audit log
        audit_id = self.audit_logger.log_update(
            update_id=update_id,
            action="applied" if apply_success else "failed",
            risk_level=risk_score.level.value,
            files_changed=changed_files,
            approved_by=approval_req.approved_by,
            test_result=True,
            applied=apply_success
        )
        
        return UpdateResult(
            success=apply_success,
            update_id=update_id,
            risk_score=risk_score,
            approval_status=approval_req.status.value,
            test_passed=True,
            applied=apply_success,
            error=apply_error,
            audit_entry_id=audit_id
        )
    
    def approve_pending(self, update_id: str, approver: str, patch_content: str, 
                       changed_files: list) -> UpdateResult:
        """Approve and apply pending update"""
        
        # Approve
        if not self.update_gate.approve(update_id, approver):
            return UpdateResult(
                success=False,
                update_id=update_id,
                risk_score=None,
                approval_status="not_found",
                test_passed=False,
                applied=False,
                error="Update not found"
            )
        
        # Get approval
        approval = self.update_gate.pending_approvals[update_id]
        
        # Run in sandbox
        sandbox_result = self.sandbox_runner.run_in_sandbox(patch_content)
        
        if not sandbox_result.success:
            audit_id = self.audit_logger.log_update(
                update_id=update_id,
                action="approved_but_failed_tests",
                risk_level=approval.risk_score.level.value,
                files_changed=changed_files,
                approved_by=approver,
                test_result=False,
                applied=False
            )
            
            return UpdateResult(
                success=False,
                update_id=update_id,
                risk_score=approval.risk_score,
                approval_status="approved",
                test_passed=False,
                applied=False,
                error=f"Tests failed: {sandbox_result.error}",
                audit_entry_id=audit_id
            )
        
        # Apply
        apply_success, apply_error = self.atomic_applier.apply_update(patch_content, update_id)
        
        audit_id = self.audit_logger.log_update(
            update_id=update_id,
            action="applied" if apply_success else "failed",
            risk_level=approval.risk_score.level.value,
            files_changed=changed_files,
            approved_by=approver,
            test_result=True,
            applied=apply_success
        )
        
        return UpdateResult(
            success=apply_success,
            update_id=update_id,
            risk_score=approval.risk_score,
            approval_status="approved",
            test_passed=True,
            applied=apply_success,
            error=apply_error,
            audit_entry_id=audit_id
        )
    
    def get_pending_approvals(self):
        """Get all pending approvals"""
        return self.update_gate.get_pending()
    
    def verify_audit_integrity(self) -> bool:
        """Verify audit log integrity"""
        return self.audit_logger.verify_integrity()
