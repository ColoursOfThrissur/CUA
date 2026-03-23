#!/usr/bin/env python3
"""
Test script to verify computer automation tool fixes
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.enhanced_filesystem_tool import FilesystemTool
from tools.experimental.BenchmarkRunnerTool import BenchmarkRunnerTool

def test_filesystem_tool():
    """Test that FilesystemTool has the required capabilities"""
    print("Testing FilesystemTool capabilities...")
    
    # Create tool with current directory as allowed root
    tool = FilesystemTool(allowed_roots=[os.getcwd()])
    
    # Check if list_files capability exists
    capabilities = tool._capabilities
    capability_names = list(capabilities.keys())
    
    print(f"Available capabilities: {capability_names}")
    
    required_capabilities = ['list_files', 'list_directory', 'read_file', 'write_file']
    
    for cap in required_capabilities:
        if cap in capability_names:
            print(f"  ✓ {cap} - FOUND")
        else:
            print(f"  ✗ {cap} - MISSING")
    
    print()

def test_benchmark_tool():
    """Test that BenchmarkRunnerTool has the required capabilities"""
    print("Testing BenchmarkRunnerTool capabilities...")
    
    # Mock orchestrator for services
    class MockOrchestrator:
        def get_services(self, tool_name):
            class MockServices:
                class MockStorage:
                    def list(self): return []
                    def save(self, id, data): pass
                    def exists(self, id): return False
                    def delete(self, id): pass
                
                class MockShell:
                    def execute(self, cmd): return {"output": "test"}
                
                class MockLogging:
                    def error(self, msg): print(f"LOG: {msg}")
                
                class MockIds:
                    def uuid(self): return "test-id"
                
                storage = MockStorage()
                shell = MockShell()
                logging = MockLogging()
                ids = MockIds()
            
            return MockServices()
    
    tool = BenchmarkRunnerTool(MockOrchestrator())
    
    # Check if required capabilities exist
    capabilities = tool._capabilities
    capability_names = list(capabilities.keys())
    
    print(f"Available capabilities: {capability_names}")
    
    required_capabilities = ['execute', 'run_suite', 'run', 'add_case']
    
    for cap in required_capabilities:
        if cap in capability_names:
            print(f"  ✓ {cap} - FOUND")
        else:
            print(f"  ✗ {cap} - MISSING")
    
    print()

def main():
    print("Testing computer automation tool fixes...")
    print("=" * 50)
    
    test_filesystem_tool()
    test_benchmark_tool()
    
    print("Test completed!")

if __name__ == "__main__":
    main()