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
        return self.execute_capability(operation, **kwargs)
    
    def _handle_analyze_task(self, **kwargs):
        task_description = kwargs.get('task_description')
        if not task_description:
            return {'success': False, 'error': 'Missing required parameter: task_description'}
        if len(task_description) > 500:
            return {'success': False, 'error': 'task_description exceeds 500 character limit'}

        dependencies = kwargs.get('dependencies', [])
        if not isinstance(dependencies, list):
            dependencies = []

        dep_results = []
        for dependency in dependencies:
            try:
                dep_id = self.services.ids.generate('dep')
                dep_prompt = f"Analyze dependency: {dependency}"
                dep_analysis = self.services.llm.generate(dep_prompt, 0.3)
                self.services.storage.save(dep_id, {'dependency': dependency, 'analysis': dep_analysis})
                dep_results.append(dep_analysis)
            except Exception as e:
                self.services.logging.error(f"Failed to process dependency '{dependency}': {e}")

        try:
            prompt = f"Analyze: {task_description}"
            if dep_results:
                prompt += f" with dependencies: {', '.join(dep_results)}"
            analysis_result = self.services.llm.generate(prompt, 0.3)
            return {'success': True, 'data': {'analysis': analysis_result}}
        except Exception as e:
            self.services.logging.error(f"Failed to analyze task: {e}")
            return {'success': False, 'error': str(e)}
