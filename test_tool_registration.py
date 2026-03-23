#!/usr/bin/env python3
"""
Test script to verify tools are properly registered in the runtime registry
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_tool_registration():
    """Test that tools are properly registered and accessible"""
    print("Testing tool registration in runtime...")
    print("=" * 50)
    
    try:
        from api.bootstrap import build_runtime
        
        # Build runtime (this registers all tools)
        runtime = build_runtime()
        
        if not runtime.system_available:
            print(f"FAIL - System not available: {runtime.init_error}")
            return
        
        registry = runtime.registry
        
        # Check registered tools
        print("Registered tools:")
        for tool in registry.tools:
            tool_name = tool.__class__.__name__
            capabilities = list(tool._capabilities.keys()) if hasattr(tool, '_capabilities') else []
            print(f"  - {tool_name}: {capabilities}")
        
        print()
        
        # Test specific tools we fixed
        test_cases = [
            ("FilesystemTool", "list_files"),
            ("BenchmarkRunnerTool", "execute"),
            ("BenchmarkRunnerTool", "run_suite"),
            ("BenchmarkRunnerTool", "add_case"),
        ]
        
        print("Testing specific capabilities:")
        for tool_name, capability in test_cases:
            # Find tool by name
            tool = None
            for t in registry.tools:
                if t.__class__.__name__ == tool_name:
                    tool = t
                    break
            
            if not tool:
                print(f"  FAIL - {tool_name} not found in registry")
                continue
            
            if capability in tool._capabilities:
                print(f"  PASS - {tool_name}.{capability} available")
            else:
                print(f"  FAIL - {tool_name}.{capability} missing")
                print(f"    Available: {list(tool._capabilities.keys())}")
        
        print()
        
        # Test capability execution through registry
        print("Testing capability execution:")
        
        # Test FilesystemTool.list_files
        try:
            result = registry.execute_tool_capability("FilesystemTool", "list_files", path=".")
            if result and result.status.value == "success":
                print("  PASS - FilesystemTool.list_files executed successfully")
            else:
                print(f"  FAIL - FilesystemTool.list_files failed: {result.error_message if result else 'No result'}")
        except Exception as e:
            print(f"  FAIL - FilesystemTool.list_files exception: {e}")
        
        # Test BenchmarkRunnerTool.execute (should work even with no data)
        try:
            result = registry.execute_tool_capability("BenchmarkRunnerTool", "execute")
            if result:
                print("  PASS - BenchmarkRunnerTool.execute executed (result may be empty)")
            else:
                print("  FAIL - BenchmarkRunnerTool.execute returned None")
        except Exception as e:
            print(f"  FAIL - BenchmarkRunnerTool.execute exception: {e}")
        
        print("\nTest completed!")
        
    except Exception as e:
        print(f"FAIL - Exception during test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_tool_registration()