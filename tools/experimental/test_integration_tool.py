"""
Test tool to verify orchestrator integration
Generated to validate tool creation flow
"""
from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel

class TestIntegrationTool(BaseTool):
    def __init__(self, orchestrator=None):
        self.description = "Test tool for orchestrator integration"
        self.services = orchestrator.get_services(self.__class__.__name__) if orchestrator else None
        super().__init__()
    
    def register_capabilities(self):
        create_capability = ToolCapability(
            name="create",
            description="Create test item",
            parameters=[
                Parameter(name="name", type=ParameterType.STRING, description="Item name", required=True)
            ],
            returns="Created item with ID",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(create_capability, self._handle_create)
        
        get_capability = ToolCapability(
            name="get",
            description="Get test item",
            parameters=[
                Parameter(name="id", type=ParameterType.STRING, description="Item ID", required=True)
            ],
            returns="Item data",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(get_capability, self._handle_get)
        
        list_capability = ToolCapability(
            name="list",
            description="List test items",
            parameters=[
                Parameter(name="limit", type=ParameterType.INTEGER, description="Max results", required=False, default=10)
            ],
            returns="List of items",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(list_capability, self._handle_list)
    
    def execute(self, operation: str, **kwargs):
        if operation == "create":
            return self._handle_create(**kwargs)
        if operation == "get":
            return self._handle_get(**kwargs)
        if operation == "list":
            return self._handle_list(**kwargs)
        raise ValueError(f"Unsupported operation: {operation}")
    
    def _handle_create(self, **kwargs):
        name = kwargs.get('name')
        if not name:
            raise ValueError("name is required")
        
        item_id = self.services.ids.generate("test")
        data = {
            "id": item_id,
            "name": name,
            "created_at": self.services.time.now_utc()
        }
        return self.services.storage.save(item_id, data)
    
    def _handle_get(self, **kwargs):
        item_id = kwargs.get('id')
        if not item_id:
            raise ValueError("id is required")
        return self.services.storage.get(item_id)
    
    def _handle_list(self, **kwargs):
        limit = kwargs.get('limit', 10)
        return {"items": self.services.storage.list(limit=limit)}
