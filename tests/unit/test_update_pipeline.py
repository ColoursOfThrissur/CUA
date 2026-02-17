"""
Test Update Pipeline
"""
import pytest
from updater.risk_scorer import RiskScorer, UpdateRiskLevel
from updater.audit_logger import AuditLogger
import tempfile
import os

@pytest.mark.unit
class TestRiskScorer:
    
    def test_blocked_files(self):
        """Test blocked files are rejected"""
        scorer = RiskScorer()
        
        result = scorer.score_update(
            ["core/immutable_brain_stem.py"],
            10
        )
        
        assert result.level == UpdateRiskLevel.BLOCKED
        assert result.requires_approval
    
    def test_high_risk_files(self):
        """Test high-risk files require approval"""
        scorer = RiskScorer()
        
        result = scorer.score_update(
            ["core/plan_validator.py", "api/server.py"],
            100
        )
        
        assert result.level in [UpdateRiskLevel.HIGH, UpdateRiskLevel.MEDIUM]
        assert result.requires_approval
    
    def test_safe_files_auto_approve(self):
        """Test safe files can auto-approve"""
        scorer = RiskScorer()
        
        result = scorer.score_update(
            ["README.md", "docs/guide.md"],
            20
        )
        
        assert result.level == UpdateRiskLevel.VERY_LOW
        assert not result.requires_approval
    
    def test_large_diff_increases_risk(self):
        """Test large diffs increase risk score"""
        scorer = RiskScorer()
        
        result_small = scorer.score_update(["tools/new_tool.py"], 10)
        result_large = scorer.score_update(["tools/new_tool.py"], 600)
        
        assert result_large.score > result_small.score

@pytest.mark.unit
class TestAuditLogger:
    
    def test_audit_log_creation(self, tmp_path):
        """Test audit log is created"""
        logger = AuditLogger(audit_dir=str(tmp_path))
        
        entry_id = logger.log_update(
            update_id="test_001",
            action="proposed",
            risk_level="low",
            files_changed=["test.py"],
            approved_by=None,
            test_result=False,
            applied=False
        )
        
        assert entry_id is not None
        assert logger.audit_file.exists()
    
    def test_audit_integrity_verification(self, tmp_path):
        """Test audit log integrity can be verified"""
        logger = AuditLogger(audit_dir=str(tmp_path))
        
        logger.log_update("test_001", "proposed", "low", ["test.py"], None, False, False)
        logger.log_update("test_002", "applied", "low", ["test.py"], "admin", True, True)
        
        assert logger.verify_integrity()
    
    def test_audit_chain_integrity(self, tmp_path):
        """Test audit entries form valid hash chain"""
        logger = AuditLogger(audit_dir=str(tmp_path))
        
        logger.log_update("test_001", "proposed", "low", ["test.py"], None, False, False)
        logger.log_update("test_002", "applied", "low", ["test.py"], "admin", True, True)
        
        entries = logger.get_recent(10)
        
        assert len(entries) == 2
        assert entries[1]['previous_hash'] == entries[0]['entry_hash']
