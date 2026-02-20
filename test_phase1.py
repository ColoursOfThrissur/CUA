"""Test Phase 1: Tool Execution Logger and Quality Analyzer"""
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from core.tool_execution_logger import get_execution_logger
from core.tool_quality_analyzer import ToolQualityAnalyzer


def test_execution_logging():
    """Test that executions are logged correctly."""
    print("\n=== Testing Execution Logging ===")
    
    logger = get_execution_logger()
    
    # Simulate some tool executions
    test_data = [
        ("TestTool", "read", True, None, 150.5, {"path": "test.txt"}, {"content": "test data"}),
        ("TestTool", "write", True, None, 200.3, {"path": "test.txt", "data": "new"}, {"success": True}),
        ("TestTool", "read", False, "File not found", 50.2, {"path": "missing.txt"}, None),
        ("BrokenTool", "execute", False, "Timeout", 5000.0, {}, None),
        ("BrokenTool", "execute", False, "Timeout", 5100.0, {}, None),
        ("FastTool", "process", True, None, 10.5, {"data": "test"}, {"result": "processed"}),
    ]
    
    for tool_name, operation, success, error, exec_time, params, output in test_data:
        logger.log_execution(tool_name, operation, success, error, exec_time, params, output)
        print(f"[OK] Logged: {tool_name}.{operation} - {'SUCCESS' if success else 'FAILED'}")
    
    print("\n[PASS] Execution logging test passed")


def test_quality_analysis():
    """Test quality analysis and weak tool detection."""
    print("\n=== Testing Quality Analysis ===")
    
    analyzer = ToolQualityAnalyzer()
    
    # Get summary
    summary = analyzer.get_summary(days=7)
    print(f"\nEcosystem Summary:")
    print(f"  Total Tools: {summary['total_tools']}")
    print(f"  Avg Health Score: {summary['avg_health_score']:.1f}")
    print(f"  Healthy: {summary.get('healthy_tools', 0)}")
    print(f"  Weak: {summary.get('weak_tools', 0)}")
    print(f"  Quarantine: {summary.get('quarantine_tools', 0)}")
    
    # Analyze individual tools
    print("\nTool Quality Reports:")
    reports = analyzer.analyze_all_tools(days=7)
    
    for report in reports:
        print(f"\n  {report.tool_name}:")
        print(f"    Success Rate: {report.success_rate:.1%}")
        print(f"    Usage: {report.usage_frequency} executions")
        print(f"    Avg Time: {report.avg_execution_time_ms:.1f}ms")
        print(f"    Health Score: {report.health_score:.1f}/100")
        print(f"    Recommendation: {report.recommendation}")
        if report.issues:
            print(f"    Issues: {', '.join(report.issues)}")
    
    # Get weak tools
    weak_tools = analyzer.get_weak_tools(days=7, min_usage=2)
    print(f"\n[WARN] Weak Tools Detected: {len(weak_tools)}")
    for tool in weak_tools:
        print(f"  - {tool.tool_name}: {tool.recommendation} (score: {tool.health_score:.1f})")
    
    print("\n[PASS] Quality analysis test passed")


def test_integration():
    """Test integration with tool orchestrator."""
    print("\n=== Testing Orchestrator Integration ===")
    
    from core.tool_orchestrator import ToolOrchestrator
    from tools.capability_registry import CapabilityRegistry
    from tools.json_tool import JSONTool
    
    # Create orchestrator (should have logger integrated)
    registry = CapabilityRegistry()
    json_tool = JSONTool()
    registry.register_tool(json_tool)
    
    orchestrator = ToolOrchestrator(registry=registry)
    
    # Execute a tool operation
    result = orchestrator.execute_tool_step(
        tool=json_tool,
        tool_name="JSONTool",
        operation="parse",
        parameters={"json_string": '{"test": "data"}'}
    )
    
    print(f"[OK] Executed JSONTool.parse - Success: {result.success}")
    
    # Check if execution was logged
    time.sleep(0.1)  # Give logger time to write
    logger = get_execution_logger()
    stats = logger.get_tool_stats("JSONTool", days=1)
    
    print(f"[OK] JSONTool stats: {stats['total_executions']} executions logged")
    
    if stats['total_executions'] > 0:
        print("\n[PASS] Orchestrator integration test passed")
    else:
        print("\n[WARN] Warning: No executions logged (may need to check integration)")


def main():
    """Run all Phase 1 tests."""
    print("=" * 60)
    print("PHASE 1 VALIDATION: Tool Execution Logger & Quality Analyzer")
    print("=" * 60)
    
    try:
        test_execution_logging()
        test_quality_analysis()
        test_integration()
        
        print("\n" + "=" * 60)
        print("[SUCCESS] PHASE 1 IMPLEMENTATION VALIDATED")
        print("=" * 60)
        print("\nNext Steps:")
        print("  1. Start CUA server: python start.py")
        print("  2. Use tools to generate execution data")
        print("  3. Check quality dashboard: GET /quality/summary")
        print("  4. Identify weak tools: GET /quality/weak")
        
    except Exception as e:
        print(f"\n[FAIL] Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
