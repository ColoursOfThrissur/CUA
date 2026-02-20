from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel

class ExecutionPlanEvaluatorTool(BaseTool):
    def __init__(self, orchestrator=None):
        self.description = "Process Management"
        self.services = orchestrator.get_services(self.__class__.__name__) if orchestrator else None
        super().__init__()
    
    def register_capabilities(self):
        evaluate_plan_capability = ToolCapability(
            name="evaluate_plan",
            description="Evaluate Plan operation",
            parameters=[
                Parameter(name='plan', type=ParameterType.STRING, description='A structured or plain-text plan to be evaluated.', required=True)
            ],
            returns="Operation result",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(evaluate_plan_capability, self._handle_evaluate_plan)
    
    def execute(self, operation: str, **kwargs):
        if operation == "evaluate_plan":
            return self._handle_evaluate_plan(**kwargs)
        
        raise ValueError(f"Unsupported operation: {operation}")
    
    def _handle_evaluate_plan(self, **kwargs):
            plan = kwargs.get('plan')
            if not plan:
                raise ValueError("Plan is required")

            prompt = f"Evaluate the following plan: {plan}"
            evaluation = self.services.llm.generate(prompt, 0.3)

            return {'evaluation': evaluation}
