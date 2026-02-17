"""
Security component tests
Tests immutable BrainStem, session permissions, and plan schema
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_immutable_brain_stem():
    """Test immutable BrainStem cannot be modified"""
    from core.immutable_brain_stem import BrainStem, RiskLevel
    
    print("Testing Immutable BrainStem...")
    
    # Test path validation
    result = BrainStem.validate_path("./output/test.txt")
    assert result.is_valid, "Valid path rejected"
    print("  [OK] Valid path accepted")
    
    # Test blocked path
    result = BrainStem.validate_path("C:\\Windows\\system32\\test.txt")
    assert not result.is_valid, "Blocked path accepted"
    assert result.risk_level == RiskLevel.BLOCKED
    print("  [OK] Blocked path rejected")
    
    # Test immutability
    try:
        BrainStem._ALLOWED_ROOTS = ("./evil",)
        assert False, "BrainStem was modified!"
    except (RuntimeError, AttributeError):
        print("  [OK] BrainStem immutable")
    
    print("Immutable BrainStem: PASSED\n")

def test_session_permissions():
    """Test per-session permission tracking"""
    from core.session_permissions import PermissionGate
    
    print("Testing Session Permissions...")
    
    gate = PermissionGate()
    
    # Test permission check
    result = gate.check_permission(
        "session_1", "filesystem_tool", "read_file", {"path": "./test.txt"}
    )
    assert result.is_valid, "Valid operation rejected"
    print("  [OK] Valid operation permitted")
    
    # Test write limit
    session = gate.get_session("session_2")
    session.files_written = 10  # Max limit
    
    result = gate.check_permission(
        "session_2", "filesystem_tool", "write_file", 
        {"path": "./test.txt", "content": "test"}
    )
    assert not result.is_valid, "Write limit not enforced"
    print("  [OK] Write limit enforced")
    
    # Test session isolation
    session_1 = gate.get_session("session_1")
    session_2 = gate.get_session("session_2")
    assert session_1.session_id != session_2.session_id
    print("  [OK] Sessions isolated")
    
    print("Session Permissions: PASSED\n")

def test_plan_schema():
    """Test strict plan schema validation"""
    from core.plan_schema import validate_plan_json
    
    print("Testing Plan Schema...")
    
    # Valid plan
    valid_plan = {
        "plan_id": "plan_123",
        "analysis": "User wants to list files in directory",
        "steps": [
            {
                "step_id": "step_1",
                "tool": "filesystem_tool",
                "operation": "list_directory",
                "parameters": {"path": "."},
                "reasoning": "List files to see what exists in current directory"
            }
        ],
        "confidence": 0.9,
        "estimated_duration": 5
    }
    
    is_valid, plan, error = validate_plan_json(valid_plan)
    assert is_valid, f"Valid plan rejected: {error}"
    print("  [OK] Valid plan accepted")
    
    # Invalid plan - missing required field
    invalid_plan = {
        "plan_id": "plan_456",
        "steps": []
    }
    
    is_valid, plan, error = validate_plan_json(invalid_plan)
    assert not is_valid, "Invalid plan accepted"
    print("  [OK] Invalid plan rejected")
    
    # Invalid operation
    invalid_op = {
        "plan_id": "plan_789",
        "analysis": "Test invalid operation",
        "steps": [
            {
                "step_id": "step_1",
                "tool": "filesystem_tool",
                "operation": "delete_everything",  # Not allowed
                "parameters": {},
                "reasoning": "This should fail validation"
            }
        ],
        "confidence": 0.5
    }
    
    is_valid, plan, error = validate_plan_json(invalid_op)
    assert not is_valid, "Invalid operation accepted"
    print("  [OK] Invalid operation rejected")
    
    print("Plan Schema: PASSED\n")

if __name__ == "__main__":
    print("=" * 50)
    print("SECURITY COMPONENT TESTS")
    print("=" * 50 + "\n")
    
    try:
        test_immutable_brain_stem()
        test_session_permissions()
        test_plan_schema()
        
        print("=" * 50)
        print("ALL TESTS PASSED")
        print("=" * 50)
        
    except AssertionError as e:
        print(f"\nTEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
