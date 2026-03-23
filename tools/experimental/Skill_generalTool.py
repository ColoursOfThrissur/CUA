from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel

class SkillGeneralTool(BaseTool):
    def __init__(self, orchestrator=None):
        self.description = "general"
        self.services = orchestrator.get_services(self.__class__.__name__) if orchestrator else None
        super().__init__()

    def register_capabilities(self):
        generate_response_capability = ToolCapability(
            name="generate_response",
            description="Operation: generate_response",
            parameters=[
                Parameter(name="prompt", type=ParameterType.STRING, description="The input text or question for which a response is needed.", required=True),
                Parameter(name="temperature", type=ParameterType.INTEGER, description="Controls the randomness of the generated response. Lower values make the output more deterministic, while higher values make it more random.", required=False),
                Parameter(name="max_tokens", type=ParameterType.INTEGER, description="The maximum number of tokens to generate in the response.", required=False),
            ],
            returns="dict",
            safety_level=SafetyLevel.MEDIUM,
            examples=[{}],
            dependencies=["self.services.llm"],
        )
        self.add_capability(generate_response_capability, self._handle_generate_response)

    def execute(self, operation: str, **kwargs):
        return self.execute_capability(operation, **kwargs)

    def _handle_generate_response(self, **kwargs):
        # Validate required inputs
        if 'prompt' not in kwargs:
            return {'success': False, 'error': 'Missing required parameter "prompt"', 'data': None}

        prompt = kwargs.get('prompt')
        temperature = kwargs.get('temperature', 0.7)  # Default to a moderate value
        max_tokens = kwargs.get('max_tokens', 150)    # Default to a reasonable length

        try:
            # Generate response using the LLM service
            response = self.services.llm.generate(
                prompt=prompt,
                temperature=temperature,
                max_tokens=max_tokens
            )
            return {'success': True, 'data': response}
        except Exception as e:
            self.services.logging.error(f"Error generating response: {e}")
            return {'success': False, 'error': str(e), 'data': None}