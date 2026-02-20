from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel

class TaskBreakdownTool(BaseTool):
    def __init__(self, orchestrator=None):
        self.description = "Project Management and Planning"
        self.services = orchestrator.get_services(self.__class__.__name__) if orchestrator else None
        super().__init__()
    
    def register_capabilities(self):
        analyze_task_capability = ToolCapability(
            name="analyze_task",
            description="Analyze Task operation",
            parameters=[
                Parameter(name='task_description', type=ParameterType.STRING, description='A high-level description of the task or goal to be broken down.', required=True)
            ],
            returns="Operation result",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(analyze_task_capability, self._handle_analyze_task)
    
    def execute(self, operation: str, **kwargs):
        if operation == "analyze_task":
            return self._handle_analyze_task(**kwargs)
        
        raise ValueError(f"Unsupported operation: {operation}")
    
    def _handle_analyze_task(self, **kwargs):
            task_description = kwargs.get('task_description')
            if not task_description:
                raise ValueError("task_description is required")

            prompt = f"Analyze: {task_description}"
            analysis_result = self.services.llm.generate(prompt, 0.3)

            return {'analysis': analysis_result}
