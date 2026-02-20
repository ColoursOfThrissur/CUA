"""Test thin tools architecture - all phases."""
import tempfile
import os
from pathlib import Path


def test_phase1_services():
    """Phase 1: Services instantiate and provide storage/time/ID."""
    from core.tool_orchestrator import ToolOrchestrator
    
    orchestrator = ToolOrchestrator()
    services = orchestrator.get_services("TestTool")
    
    assert services.storage is not None
    assert services.time is not None
    assert services.ids is not None
    
    # Test ID generation
    id1 = services.ids.generate("test")
    assert id1.startswith("test_")
    
    # Test time
    now = services.time.now_utc()
    assert "T" in now
    
    print("[OK] Phase 1: Services working")


def test_phase2_validation():
    """Phase 2: ValidationService validates from ToolCapability."""
    from core.validation_service import ValidationService
    from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel
    
    cap = ToolCapability(
        name="create",
        description="Create item",
        parameters=[
            Parameter(name="id", type=ParameterType.STRING, description="ID", required=True),
            Parameter(name="count", type=ParameterType.INTEGER, description="Count", required=False, default=1)
        ],
        returns="Created item",
        safety_level=SafetyLevel.LOW,
        examples=[],
        dependencies=[]
    )
    
    # Valid params
    result = ValidationService.validate(cap, {"id": "test123", "count": "5"})
    assert result.valid
    assert result.sanitized["id"] == "test123"
    assert result.sanitized["count"] == 5  # Auto-converted
    
    # Missing required
    result = ValidationService.validate(cap, {"count": 1})
    assert not result.valid
    assert "Missing required parameter: id" in result.errors
    
    print("[OK] Phase 2: Validation working")


def test_phase3_advanced_storage():
    """Phase 3: Advanced storage methods (find, count, update)."""
    from core.tool_orchestrator import ToolOrchestrator
    import time
    
    tmpdir = tempfile.mkdtemp()
    original = os.getcwd()
    try:
        os.chdir(tmpdir)
        os.makedirs("data/test", exist_ok=True)
        
        orchestrator = ToolOrchestrator()
        services = orchestrator.get_services("TestTool")
        
        # Create items
        services.storage.save("item1", {"name": "Alice", "age": 30})
        services.storage.save("item2", {"name": "Bob", "age": 25})
        services.storage.save("item3", {"name": "Charlie", "age": 35})
        
        # Count
        count = services.storage.count()
        assert count == 3
        
        # Find
        results = services.storage.find(lambda x: x.get("age", 0) > 28)
        assert len(results) == 2
        
        # Update
        updated = services.storage.update("item1", {"age": 31})
        assert updated["age"] == 31
        assert updated["name"] == "Alice"
        
        print("[OK] Phase 3: Advanced storage working")
    finally:
        os.chdir(original)
        time.sleep(0.1)
        try:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)
        except:
            pass


def test_phase4_orchestrator_integration():
    """Phase 4: Orchestrator validates and wraps thin tool results."""
    from core.tool_orchestrator import ToolOrchestrator
    from tools.tool_interface import BaseTool
    from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel
    import time
    
    class ThinTestTool(BaseTool):
        def __init__(self, orchestrator=None):
            self.name = "ThinTestTool"
            self.services = orchestrator.get_services(self.name) if orchestrator else None
            super().__init__()
        
        def register_capabilities(self):
            cap = ToolCapability(
                name="create",
                description="Create item",
                parameters=[
                    Parameter(name="id", type=ParameterType.STRING, description="ID", required=True),
                    Parameter(name="name", type=ParameterType.STRING, description="Name", required=True)
                ],
                returns="Created item",
                safety_level=SafetyLevel.LOW,
                examples=[],
                dependencies=[]
            )
            self.add_capability(cap, self._handle_create)
        
        def execute(self, operation: str, **kwargs):
            if operation == "create":
                return self._handle_create(**kwargs)
            raise ValueError(f"Unknown operation: {operation}")
        
        def _handle_create(self, **kwargs):
            # Thin tool: return plain dict, raise on error
            item_id = kwargs.get("id")
            name = kwargs.get("name")
            data = {"id": item_id, "name": name}
            return self.services.storage.save(item_id, data)
    
    tmpdir = tempfile.mkdtemp()
    original = os.getcwd()
    try:
        os.chdir(tmpdir)
        os.makedirs("data/thintesttool", exist_ok=True)
        
        orchestrator = ToolOrchestrator()
        tool = ThinTestTool(orchestrator=orchestrator)
        
        # Valid execution
        result = orchestrator.execute_tool_step(
            tool=tool,
            tool_name="ThinTestTool",
            operation="create",
            parameters={"id": "test1", "name": "Alice"}
        )
        assert result.success
        assert result.data["name"] == "Alice"
        
        # Validation failure (missing required)
        result = orchestrator.execute_tool_step(
            tool=tool,
            tool_name="ThinTestTool",
            operation="create",
            parameters={"id": "test2"}
        )
        assert not result.success
        assert "Validation failed" in result.error or "Missing required" in result.error
        
        print("[OK] Phase 4: Orchestrator integration working")
    finally:
        os.chdir(original)
        time.sleep(0.1)
        try:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)
        except:
            pass


if __name__ == "__main__":
    original_cwd = os.getcwd()
    try:
        test_phase1_services()
        test_phase2_validation()
        test_phase3_advanced_storage()
        test_phase4_orchestrator_integration()
        print("\n[SUCCESS] All phases complete - thin tools architecture working!")
    finally:
        os.chdir(original_cwd)
