"""
Quick verification script for inter-tool communication changes
Run this to verify all changes are working correctly
"""

def verify_imports():
    """Verify all imports work"""
    print("✓ Checking imports...")
    try:
        from tools.capability_registry import CapabilityRegistry
        from core.tool_orchestrator import ToolOrchestrator
        from core.tool_services import ToolServices
        from tools.enhanced_filesystem_tool import FilesystemTool
        print("  ✓ All imports successful")
        return True
    except Exception as e:
        print(f"  ✗ Import failed: {e}")
        return False


def verify_orchestrator_with_registry():
    """Verify orchestrator accepts registry"""
    print("✓ Checking orchestrator with registry...")
    try:
        from tools.capability_registry import CapabilityRegistry
        from core.tool_orchestrator import ToolOrchestrator
        
        registry = CapabilityRegistry()
        orchestrator = ToolOrchestrator(registry=registry)
        
        assert orchestrator._registry is registry
        print("  ✓ Orchestrator accepts registry")
        return True
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False


def verify_services_have_references():
    """Verify services get orchestrator and registry"""
    print("✓ Checking services references...")
    try:
        from tools.capability_registry import CapabilityRegistry
        from core.tool_orchestrator import ToolOrchestrator
        
        registry = CapabilityRegistry()
        orchestrator = ToolOrchestrator(registry=registry)
        services = orchestrator.get_services("TestTool")
        
        assert services.orchestrator is orchestrator
        assert services.registry is registry
        assert hasattr(services, 'call_tool')
        assert hasattr(services, 'list_tools')
        assert hasattr(services, 'has_capability')
        print("  ✓ Services have all references and methods")
        return True
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False


def verify_tool_discovery():
    """Verify tool discovery works"""
    print("✓ Checking tool discovery...")
    try:
        from tools.capability_registry import CapabilityRegistry
        from core.tool_orchestrator import ToolOrchestrator
        from tools.enhanced_filesystem_tool import FilesystemTool
        
        registry = CapabilityRegistry()
        orchestrator = ToolOrchestrator(registry=registry)
        
        # Register a tool
        fs_tool = FilesystemTool(orchestrator=orchestrator)
        registry.register_tool(fs_tool)
        
        # Get services
        services = orchestrator.get_services("TestTool")
        
        # Test discovery
        tools = services.list_tools()
        assert "FilesystemTool" in tools
        
        has_read = services.has_capability("read_file")
        assert has_read is True
        
        has_fake = services.has_capability("fake_capability")
        assert has_fake is False
        
        print("  ✓ Tool discovery working")
        return True
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False


def verify_backward_compatibility():
    """Verify backward compatibility"""
    print("✓ Checking backward compatibility...")
    try:
        from tools.enhanced_filesystem_tool import FilesystemTool
        
        # Tool should work without orchestrator
        fs_tool = FilesystemTool()
        assert fs_tool is not None
        
        print("  ✓ Backward compatibility maintained")
        return True
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False


def main():
    """Run all verification checks"""
    print("\n" + "="*60)
    print("INTER-TOOL COMMUNICATION - VERIFICATION")
    print("="*60 + "\n")
    
    checks = [
        verify_imports,
        verify_orchestrator_with_registry,
        verify_services_have_references,
        verify_tool_discovery,
        verify_backward_compatibility,
    ]
    
    results = []
    for check in checks:
        try:
            result = check()
            results.append(result)
        except Exception as e:
            print(f"  ✗ Unexpected error: {e}")
            results.append(False)
        print()
    
    print("="*60)
    passed = sum(results)
    total = len(results)
    
    if passed == total:
        print(f"✓ ALL CHECKS PASSED ({passed}/{total})")
        print("✓ Inter-tool communication is working correctly!")
    else:
        print(f"✗ SOME CHECKS FAILED ({passed}/{total})")
        print("✗ Please review the errors above")
    
    print("="*60 + "\n")
    
    return passed == total


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
