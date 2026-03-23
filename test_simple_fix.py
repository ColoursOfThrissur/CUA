#!/usr/bin/env python3
"""
Simple test script to verify computer automation tool fixes
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.enhanced_filesystem_tool import FilesystemTool
from tools.experimental.BenchmarkRunnerTool import BenchmarkRunnerTool

def test_fixes():
    """Test that the fixes work"""
    print("Testing computer automation tool fixes...")
    print("=" * 50)
    
    # Test FilesystemTool
    print("FilesystemTool capabilities:")
    tool = FilesystemTool(allowed_roots=[os.getcwd()])
    capabilities = list(tool._capabilities.keys())
    print(f"  Available: {capabilities}")
    
    required = ['list_files', 'list_directory', 'read_file', 'write_file']
    missing = [cap for cap in required if cap not in capabilities]
    
    if not missing:
        print("  PASS - All required capabilities found")
    else:
        print(f"  FAIL - Missing: {missing}")
    
    print()
    
    # Test BenchmarkRunnerTool
    print("BenchmarkRunnerTool capabilities:")
    
    class MockOrchestrator:
        def get_services(self, tool_name):
            class MockServices:
                class MockStorage:
                    def list(self): return []
                storage = MockStorage()
                shell = None
                logging = None
                ids = None
            return MockServices()
    
    benchmark_tool = BenchmarkRunnerTool(MockOrchestrator())
    benchmark_capabilities = list(benchmark_tool._capabilities.keys())
    print(f"  Available: {benchmark_capabilities}")
    
    required_benchmark = ['execute', 'run_suite', 'run', 'add_case']
    missing_benchmark = [cap for cap in required_benchmark if cap not in benchmark_capabilities]
    
    if not missing_benchmark:
        print("  PASS - All required capabilities found")
    else:
        print(f"  FAIL - Missing: {missing_benchmark}")
    
    print("\nTest completed!")

if __name__ == "__main__":
    test_fixes()