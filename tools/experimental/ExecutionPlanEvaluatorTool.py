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

        evaluate_capability = ToolCapability(
            name="evaluate",
            description="Evaluate multiple plans in parallel using the LLM.",
            parameters=[
                Parameter(name='plans', type=ParameterType.LIST, description='List of plans to evaluate in parallel', required=True)
            ],
            returns="Operation result",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(evaluate_capability, self._handle_evaluate)
        self.add_capability(evaluate_plan_capability, self._handle_evaluate_plan)
    
    def _handle_evaluate(self, **kwargs) -> dict:
        plans = kwargs.get('plans')
        if not plans or not isinstance(plans, list):
            return {'error': 'Missing or invalid parameter: plans (must be a list)'}
        try:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            def _eval_one(plan):
                prompt = f"Evaluate the following plan: {plan}"
                evaluation = self.services.llm.generate(prompt, 0.3)
                return {'plan': plan, 'evaluation': evaluation}

            results = []
            with ThreadPoolExecutor(max_workers=min(len(plans), 4)) as executor:
                futures = {executor.submit(_eval_one, p): p for p in plans}
                for future in as_completed(futures):
                    try:
                        results.append(future.result())
                    except Exception as e:
                        results.append({'plan': futures[future], 'evaluation': None, 'error': str(e)})
            return {'success': True, 'evaluations': results}
        except Exception as e:
            self.services.logging.error(f"Operation failed: {e}")
            return {'success': False, 'error': str(e)}

    def execute(self, operation: str, **kwargs):
        if operation == "evaluate_plan":
            return self._handle_evaluate_plan(**kwargs)
        
        if operation == "evaluate":
            return self._handle_evaluate(**kwargs)

        raise ValueError(f"Unsupported operation: {operation}")
    
    def _handle_evaluate_plan(self, **kwargs):
            plans = kwargs.get('plan', [])
            if not isinstance(plans, list):
                plans = [plans]

            evaluations = []
            for plan in plans:
                prompt = f"Evaluate the following plan: {plan}"
                try:
                    evaluation = self.services.llm.generate(prompt, 0.3)
                    evaluations.append({'plan': plan, 'evaluation': evaluation})
                except Exception as e:
                    self.services.logging.error(f"Error evaluating plan: {plan}. Error: {str(e)}")
                    evaluations.append({'plan': plan, 'evaluation': None})

            return {'evaluations': evaluations}
