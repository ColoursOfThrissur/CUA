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
            names = kwargs.get('names', [kwargs.get('name')])
            if not names:
                raise ValueError("name(s) is required")

            items = []
            for name in names:
                item_id = self.services.ids.generate("test")
                data = {
                    "id": item_id,
                    "name": name,
                    "created_at": self.services.time.now_utc()
                }
                items.append(data)

            results = [self.services.storage.save(item['id'], item) for item in items]
            return {"results": results}
    
    def _handle_get(self, **kwargs):
            item_id = kwargs.get('id')
            if not item_id:
                raise ValueError("id is required")

            if isinstance(item_id, list):
                return [self.services.storage.get(i) for i in item_id]

            return self.services.storage.get(item_id)
    
    def _handle_list(self, **kwargs):
            limit = kwargs.get('limit', 10)
            try:
                items = self.services.storage.list(limit=limit)
                batch_size = 5
                batches = [items[i:i + batch_size] for i in range(0, len(items), batch_size)]
                processed_items = []
                for batch in batches:
                    # Example processing: generate a summary for each item
                    for item in batch:
                        summary = self.services.llm.generate(prompt=item, temperature=0.5, max_tokens=100)
                        processed_items.append({"item": item, "summary": summary})
                return {"items": processed_items}
            except Exception as e:
                self.services.logging.error(f"Error processing items: {e}")
                return {"error": str(e)}
