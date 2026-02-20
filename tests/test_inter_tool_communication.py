"""
Test inter-tool communication capabilities
"""
import pytest
from tools.capability_registry import CapabilityRegistry
from core.tool_orchestrator import ToolOrchestrator
from tools.enhanced_filesystem_tool import FilesystemTool
from tools.http_tool import HTTPTool


def test_orchestrator_with_registry():
    """Test orchestrator initialization with registry"""
    registry = CapabilityRegistry()
    orchestrator = ToolOrchestrator(registry=registry)
    
    assert orchestrator._registry is registry


def test_services_have_orchestrator_and_registry():
    """Test that services get orchestrator and registry references"""
    registry = CapabilityRegistry()
    orchestrator = ToolOrchestrator(registry=registry)
    
    services = orchestrator.get_services("TestTool")
    
    assert services.orchestrator is orchestrator
    assert services.registry is registry


def test_tool_can_list_available_tools():
    """Test that tools can discover other tools"""
    registry = CapabilityRegistry()
    orchestrator = ToolOrchestrator(registry=registry)
    
    # Register some tools
    fs_tool = FilesystemTool(orchestrator=orchestrator)
    http_tool = HTTPTool(orchestrator=orchestrator)
    registry.register_tool(fs_tool)
    registry.register_tool(http_tool)
    
    # Get services for a tool
    services = orchestrator.get_services("TestTool")
    
    # Tool can list available tools
    available_tools = services.list_tools()
    assert "FilesystemTool" in available_tools
    assert "HTTPTool" in available_tools


def test_tool_can_check_capabilities():
    """Test that tools can check if capabilities exist"""
    registry = CapabilityRegistry()
    orchestrator = ToolOrchestrator(registry=registry)
    
    # Register filesystem tool
    fs_tool = FilesystemTool(orchestrator=orchestrator)
    registry.register_tool(fs_tool)
    
    # Get services
    services = orchestrator.get_services("TestTool")
    
    # Check capabilities
    assert services.has_capability("read_file")
    assert services.has_capability("write_file")
    assert not services.has_capability("nonexistent_capability")


def test_tool_can_call_another_tool(tmp_path):
    """Test that tools can call other tools via services"""
    registry = CapabilityRegistry()
    orchestrator = ToolOrchestrator(registry=registry)
    
    # Register filesystem tool
    fs_tool = FilesystemTool(orchestrator=orchestrator, allowed_roots=[str(tmp_path)])
    registry.register_tool(fs_tool)
    
    # Create test file
    test_file = tmp_path / "test.txt"
    test_file.write_text("Hello World")
    
    # Get services for another tool
    services = orchestrator.get_services("CallerTool")
    
    # Call filesystem tool from services
    result = services.call_tool(
        tool_name="FilesystemTool",
        operation="read_file",
        path=str(test_file)
    )
    
    assert result == "Hello World"


def test_inter_tool_call_error_handling():
    """Test error handling in inter-tool calls"""
    registry = CapabilityRegistry()
    orchestrator = ToolOrchestrator(registry=registry)
    
    services = orchestrator.get_services("TestTool")
    
    # Call non-existent tool
    with pytest.raises(ValueError, match="Tool 'NonExistentTool' not found"):
        services.call_tool("NonExistentTool", "operation")


def test_services_without_orchestrator():
    """Test that services fail gracefully without orchestrator"""
    from core.tool_services import ToolServices
    from core.storage_broker import StorageBroker
    
    # Create services without orchestrator
    broker = StorageBroker("TestTool")
    services = ToolServices("TestTool", broker)
    
    # Should not have orchestrator or registry
    assert services.orchestrator is None
    assert services.registry is None
    
    # Inter-tool calls should fail with clear error
    with pytest.raises(RuntimeError, match="Inter-tool calls require orchestrator and registry"):
        services.call_tool("SomeTool", "operation")
    
    # Discovery methods should return safe defaults
    assert services.list_tools() == []
    assert services.has_capability("anything") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
