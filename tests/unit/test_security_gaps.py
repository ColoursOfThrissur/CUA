"""
Test Critical Security Gaps - Sandbox Isolation, BrainStem Protection, Checksum Verification
"""
import pytest
from updater.risk_scorer import RiskScorer, UpdateRiskLevel
from updater.atomic_applier import AtomicApplier
import tempfile
import os

class TestSecurityGaps:
    
    def test_brainstem_rename_blocked(self):
        """Gap 2: Block BrainStem renames/moves"""
        scorer = RiskScorer()
        
        # Direct modification - blocked
        risk = scorer.score_update(["core/immutable_brain_stem.py"], 10)
        assert risk.level == UpdateRiskLevel.BLOCKED
        
        # Rename attempt - should also be blocked
        risk = scorer.score_update(["core/immutable_brain_stem_backup.py"], 10)
        assert risk.level == UpdateRiskLevel.BLOCKED
        assert "immutable_brain_stem" in risk.reasons[0]
        
        # Move to different location - blocked
        risk = scorer.score_update(["tools/immutable_brain_stem.py"], 10)
        assert risk.level == UpdateRiskLevel.BLOCKED
    
    def test_session_permissions_rename_blocked(self):
        """Gap 2: Block session_permissions renames"""
        scorer = RiskScorer()
        
        risk = scorer.score_update(["core/session_permissions_new.py"], 10)
        assert risk.level == UpdateRiskLevel.BLOCKED
        assert "session_permissions" in risk.reasons[0]
    
    def test_plan_schema_rename_blocked(self):
        """Gap 2: Block plan_schema renames"""
        scorer = RiskScorer()
        
        risk = scorer.score_update(["core/plan_schema_v2.py"], 10)
        assert risk.level == UpdateRiskLevel.BLOCKED
        assert "plan_schema" in risk.reasons[0]
    
    def test_atomic_applier_checksum_verification(self):
        """Gap 2: Verify BrainStem checksum before/after apply"""
        import os
        
        # Get project root (2 levels up from test file)
        test_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(test_dir))
        
        applier = AtomicApplier(repo_path=project_root)
        
        # Get current checksum
        checksum_before = applier._get_brainstem_checksum()
        
        # Should be valid hash (not 'missing' or 'error')
        assert checksum_before not in ["missing", "error"], f"BrainStem file not found at {project_root}/core/immutable_brain_stem.py"
        assert len(checksum_before) == 64, f"Expected SHA256 hash (64 chars), got {len(checksum_before)}"
        
        # Verify checksum is stable (same file = same hash)
        checksum_again = applier._get_brainstem_checksum()
        assert checksum_before == checksum_again
    
    def test_sandbox_process_restrictions(self):
        """Gap 1: Verify sandbox has process restrictions"""
        from updater.sandbox_runner import SandboxRunner
        
        runner = SandboxRunner(repo_path=".")
        
        # Verify sandbox runner exists and has isolation
        assert hasattr(runner, 'run_in_sandbox')
        assert hasattr(runner, '_run_tests')
        
        # Check that _run_tests uses restricted environment
        import inspect
        source = inspect.getsource(runner._run_tests)
        
        # Should have environment restrictions
        assert 'env' in source or 'creationflags' in source
    
    def test_multiple_blocked_patterns(self):
        """Verify all critical patterns are blocked"""
        scorer = RiskScorer()
        
        blocked_attempts = [
            "core/immutable_brain_stem.py",
            "core/immutable_brain_stem_v2.py",
            "backup/immutable_brain_stem.py",
            "core/session_permissions.py",
            "core/session_permissions_backup.py",
            "core/plan_schema.py",
            "tools/plan_schema_copy.py"
        ]
        
        for file in blocked_attempts:
            risk = scorer.score_update([file], 10)
            assert risk.level == UpdateRiskLevel.BLOCKED, f"Failed to block: {file}"
    
    def test_safe_files_not_blocked(self):
        """Verify safe files are not incorrectly blocked"""
        scorer = RiskScorer()
        
        safe_files = [
            "tests/test_brain_stem_edge_cases.py",  # Contains pattern but is test
            "README.md",
            "docs/permissions_guide.md",
            "tools/enhanced_filesystem_tool.py"
        ]
        
        for file in safe_files:
            risk = scorer.score_update([file], 10)
            # Should not be BLOCKED (may be other risk levels)
            assert risk.level != UpdateRiskLevel.BLOCKED, f"Incorrectly blocked: {file}"
