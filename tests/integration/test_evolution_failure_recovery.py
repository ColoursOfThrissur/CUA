"""Integration tests for evolution failure recovery strategies."""
import pytest
from unittest.mock import Mock, patch


class TestEvolutionFailureRecovery:
    """Test evolution failure classification and recovery strategies."""
    
    def test_infra_failure_detection(self):
        """Test INFRA failure type detection."""
        from infrastructure.failure_handling.evolution_failure_classifier import EvolutionFailureClassifier
        
        classifier = EvolutionFailureClassifier()
        
        # Simulate analysis step failure with FileNotFoundError
        result = classifier.classify_failure(
            step="analysis",
            error_message="Could not analyze tool: FileNotFoundError",
            failure_history=[]
        )
        
        assert result["failure_type"] == "INFRA"
        assert "deterministic" in result["strategy"].lower()
    
    def test_overflow_failure_detection(self):
        """Test OVERFLOW failure type detection for large files."""
        from infrastructure.failure_handling.evolution_failure_classifier import EvolutionFailureClassifier
        
        classifier = EvolutionFailureClassifier()
        
        # Simulate code generation failure with empty output on large file
        result = classifier.classify_failure(
            step="code_generation",
            error_message="",
            failure_history=[],
            file_size=10000  # > 8KB threshold
        )
        
        assert result["failure_type"] == "OVERFLOW"
        assert "chunk" in result["strategy"].lower()
    
    def test_pattern_loop_detection(self):
        """Test PATTERN_LOOP detection for repeated errors."""
        from infrastructure.failure_handling.evolution_failure_classifier import EvolutionFailureClassifier
        
        classifier = EvolutionFailureClassifier()
        error_msg = "validation failed: missing return statement"
        
        result = classifier.classify_failure(
            step="validation",
            error_message=error_msg,
            failure_history=[
                {"step": "validation", "error": error_msg},
                {"step": "validation", "error": error_msg},
            ]
        )
        
        assert result["failure_type"] == "PATTERN_LOOP"
        assert "constraint" in result["strategy"].lower()
    
    def test_dep_blocked_detection(self):
        """Test DEP_BLOCKED detection for missing dependencies."""
        from infrastructure.failure_handling.evolution_failure_classifier import EvolutionFailureClassifier
        
        classifier = EvolutionFailureClassifier()
        
        result = classifier.classify_failure(
            step="dependency_check",
            error_message="dependency 'pandas' not available",
            failure_history=[]
        )
        
        assert result["failure_type"] == "DEP_BLOCKED"
        assert "alternative" in result["strategy"].lower()
    
    def test_constraint_memory_persistence(self):
        """Test that constraints are persisted in cua.db."""
        from application.evolution.evolution_constraint_memory import EvolutionConstraintMemory
        
        memory = EvolutionConstraintMemory()
        
        # Record a blocked dependency
        memory.add_constraint(
            tool_name="TestTool",
            constraint_type="blocked_lib",
            value="pandas",
            reason="Not available in environment"
        )
        
        # Retrieve constraints
        constraints = memory.get_constraints("TestTool")
        
        assert "pandas" in constraints.get("blocked_libs", [])
        
        # Verify persistence across instances
        memory2 = EvolutionConstraintMemory()
        constraints2 = memory2.get_constraints("TestTool")
        assert "pandas" in constraints2.get("blocked_libs", [])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
