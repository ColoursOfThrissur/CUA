"""
Test Self-Evolution System
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.self_evolution import SandboxedEvolution, CapabilityUpdate

def test_self_evolution():
    """Test capability update with sandbox and rollback"""
    
    print("=" * 50)
    print("SELF-EVOLUTION SYSTEM TEST")
    print("=" * 50 + "\n")
    
    # Initialize evolution system
    evolution = SandboxedEvolution()
    print("Evolution system initialized\n")
    
    # Create test capability
    test_capability = """
from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel

class TestTool(BaseTool):
    def register_capabilities(self):
        cap = ToolCapability(
            name="test_operation",
            description="Test operation",
            parameters=[Parameter("input", ParameterType.STRING, "Test input")],
            returns="Test output",
            safety_level=SafetyLevel.LOW,
            examples=[{"input": "test"}]
        )
        self.add_capability(cap, self._handle_test)
    
    def _handle_test(self, input: str) -> str:
        return f"Processed: {input}"
"""
    
    # Create test code
    test_code = """
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_capability():
    from test_tool import TestTool
    tool = TestTool()
    result = tool.execute_capability("test_operation", input="hello")
    assert result.status.value == "success"
    assert "Processed: hello" in str(result.data)
    print("Test passed")

if __name__ == "__main__":
    test_capability()
"""
    
    # Propose update
    print("Step 1: Proposing capability update...")
    update = CapabilityUpdate(
        capability_name="test",
        code=test_capability,
        test_code=test_code,
        version="1.0.0"
    )
    
    result = evolution.propose_update(update)
    
    print(f"  Update result: {'SUCCESS' if result.success else 'FAILED'}")
    print(f"  Tests passed: {result.tests_passed}")
    print(f"  Rollback available: {result.rollback_available}")
    
    if result.error:
        print(f"  Error: {result.error}")
    
    print("\n" + "=" * 50)
    print("SELF-EVOLUTION TEST COMPLETED")
    print("=" * 50)

if __name__ == "__main__":
    try:
        test_self_evolution()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
