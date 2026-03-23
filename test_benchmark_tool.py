"""
Test script for BenchmarkRunnerTool
"""
import sys
sys.path.insert(0, '.')

from core.tool_orchestrator import ToolOrchestrator
from core.tool_registry import ToolRegistry

def test_benchmark_tool():
    print("=== Testing BenchmarkRunnerTool ===\n")
    
    # Initialize orchestrator
    registry = ToolRegistry()
    orchestrator = ToolOrchestrator(registry)
    
    # Test 1: Add a benchmark case
    print("Test 1: Adding benchmark case...")
    result1 = orchestrator.execute_tool_step(
        tool_name="BenchmarkRunnerTool",
        operation="add_benchmark_case",
        parameters={
            "task_description": "echo 'Hello CUA'",
            "expected_result": "Hello CUA"
        }
    )
    print(f"Result: {result1.data}")
    print(f"Success: {result1.success}\n")
    
    if result1.success:
        case_id = result1.data.get("case_id")
        print(f"Created case ID: {case_id}\n")
        
        # Test 2: Add another benchmark case
        print("Test 2: Adding second benchmark case...")
        result2 = orchestrator.execute_tool_step(
            tool_name="BenchmarkRunnerTool",
            operation="add_benchmark_case",
            parameters={
                "task_description": "echo 'Test 123'",
                "expected_result": "Test 123"
            }
        )
        print(f"Result: {result2.data}")
        print(f"Success: {result2.success}\n")
        
        # Test 3: Run benchmark suite
        print("Test 3: Running benchmark suite...")
        result3 = orchestrator.execute_tool_step(
            tool_name="BenchmarkRunnerTool",
            operation="run_benchmark_suite",
            parameters={}
        )
        print(f"Result: {result3.data}")
        print(f"Success: {result3.success}\n")
        
        # Test 4: Remove a benchmark case
        print(f"Test 4: Removing benchmark case {case_id}...")
        result4 = orchestrator.execute_tool_step(
            tool_name="BenchmarkRunnerTool",
            operation="remove_benchmark_case",
            parameters={"case_id": case_id}
        )
        print(f"Result: {result4.data}")
        print(f"Success: {result4.success}\n")
        
        # Test 5: Run suite again (should have one less case)
        print("Test 5: Running benchmark suite after removal...")
        result5 = orchestrator.execute_tool_step(
            tool_name="BenchmarkRunnerTool",
            operation="run_benchmark_suite",
            parameters={}
        )
        print(f"Result: {result5.data}")
        print(f"Success: {result5.success}\n")
    
    print("=== Test Complete ===")

if __name__ == "__main__":
    test_benchmark_tool()
