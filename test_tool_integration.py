"""
Validation script for tool creation flow
Tests that generated tools work with orchestrator
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

def test_orchestrator_integration():
    """Test that generated tool works with orchestrator"""
    from core.tool_orchestrator import ToolOrchestrator
    from tools.capability_registry import CapabilityRegistry
    from tools.experimental.test_integration_tool import TestIntegrationTool
    
    print("=" * 60)
    print("TESTING ORCHESTRATOR INTEGRATION")
    print("=" * 60)
    
    # Initialize orchestrator
    registry = CapabilityRegistry()
    orchestrator = ToolOrchestrator(registry=registry)
    
    # Create tool instance
    tool = TestIntegrationTool(orchestrator=orchestrator)
    
    # Test 1: Check services are injected
    print("\n[TEST 1] Services injection")
    assert tool.services is not None, "Services not injected"
    assert hasattr(tool.services, 'storage'), "Storage service missing"
    assert hasattr(tool.services, 'ids'), "ID service missing"
    assert hasattr(tool.services, 'time'), "Time service missing"
    print("[PASS] Services properly injected")
    
    # Test 2: Check capabilities registered
    print("\n[TEST 2] Capability registration")
    caps = tool.get_capabilities()
    assert len(caps) == 3, f"Expected 3 capabilities, got {len(caps)}"
    assert "create" in caps, "create capability missing"
    assert "get" in caps, "get capability missing"
    assert "list" in caps, "list capability missing"
    print(f"[PASS] All 3 capabilities registered: {list(caps.keys())}")
    
    # Test 3: Execute via orchestrator (create)
    print("\n[TEST 3] Execute create operation")
    result = orchestrator.execute_tool_step(
        tool=tool,
        tool_name="TestIntegrationTool",
        operation="create",
        parameters={"name": "test_item"},
        context={}
    )
    assert result.success, f"Create failed: {result.error}"
    assert result.data is not None, "No data returned"
    assert "id" in result.data, "ID not in result"
    item_id = result.data["id"]
    print(f"[PASS] Created item: {item_id}")
    
    # Test 4: Execute via orchestrator (get)
    print("\n[TEST 4] Execute get operation")
    result = orchestrator.execute_tool_step(
        tool=tool,
        tool_name="TestIntegrationTool",
        operation="get",
        parameters={"id": item_id},
        context={}
    )
    assert result.success, f"Get failed: {result.error}"
    assert result.data["name"] == "test_item", "Wrong data retrieved"
    print(f"[PASS] Retrieved item: {result.data['name']}")
    
    # Test 5: Execute via orchestrator (list)
    print("\n[TEST 5] Execute list operation")
    result = orchestrator.execute_tool_step(
        tool=tool,
        tool_name="TestIntegrationTool",
        operation="list",
        parameters={"limit": 5},
        context={}
    )
    assert result.success, f"List failed: {result.error}"
    assert "items" in result.data, "Items not in result"
    print(f"[PASS] Listed {len(result.data['items'])} items")
    
    # Test 6: Thin tool pattern (returns dict, not ToolResult)
    print("\n[TEST 6] Thin tool pattern validation")
    raw_result = tool._handle_create(name="direct_call")
    assert isinstance(raw_result, dict), f"Expected dict, got {type(raw_result)}"
    assert "id" in raw_result, "Direct call should return dict with id"
    print("[PASS] Thin tool returns plain dict (orchestrator wraps it)")
    
    # Test 7: Error handling
    print("\n[TEST 7] Error handling")
    result = orchestrator.execute_tool_step(
        tool=tool,
        tool_name="TestIntegrationTool",
        operation="get",
        parameters={"id": "nonexistent"},
        context={}
    )
    assert not result.success, "Should fail for nonexistent item"
    assert result.error is not None, "Should have error message"
    print(f"[PASS] Error properly handled: {result.error[:50]}...")
    
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
    print("\nConclusion:")
    print("- Generated tools work correctly with orchestrator")
    print("- Services are properly injected")
    print("- Capabilities register correctly")
    print("- Thin tool pattern works (dict returns)")
    print("- Error handling works")
    print("- Tool creation flow is VALIDATED")
    
    return True

if __name__ == "__main__":
    try:
        test_orchestrator_integration()
        sys.exit(0)
    except Exception as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
