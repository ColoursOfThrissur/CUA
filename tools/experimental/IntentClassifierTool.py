"""
IntentClassifierTool - Classifies user intent and routes requests appropriately
"""
from tools.tool_interface import BaseTool
from tools.tool_result import ToolResult, ResultStatus
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel

class IntentClassifierTool(BaseTool):
    """Classifies user intent to distinguish conversational vs actionable requests."""
    
    def __init__(self, orchestrator=None):
        self.description = "Classifies user intent and suggests appropriate tool routing"
        self.services = orchestrator.get_services(self.__class__.__name__) if orchestrator else None
        self.cache = {}
        super().__init__()

    def register_capabilities(self):
        """Register tool capabilities"""
        classify_intent_capability = ToolCapability(
            name='classify_intent',
            description='Classify user input as conversational, actionable, or meta-question',
            parameters=[
                Parameter(name='user_input', type=ParameterType.STRING, description='The user input text to classify', required=True)
            ],
            returns="Intent classification with confidence score",
            safety_level=SafetyLevel.LOW,
            examples=[
                "what tool should we add next? -> conversational",
                "analyze the sentiment of this text -> actionable"
            ],
            dependencies=[]
        )
        self.add_capability(classify_intent_capability, self._handle_classify_intent)

        suggest_tool_capability = ToolCapability(
            name='suggest_tool',
            description='Suggest which tool to use for a given actionable request',
            parameters=[
                Parameter(name='user_input', type=ParameterType.STRING, description='The actionable user request', required=True),
                Parameter(name='available_tools', type=ParameterType.LIST, description='List of available tool names', required=False, default=[])
            ],
            returns="Suggested tool name and parameters",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(suggest_tool_capability, self._handle_suggest_tool)

        extract_entities_capability = ToolCapability(
            name='extract_entities',
            description='Extract key entities and parameters from user input',
            parameters=[
                Parameter(name='user_input', type=ParameterType.STRING, description='The user input to extract entities from', required=True)
            ],
            returns="Dictionary of extracted entities",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(extract_entities_capability, self._handle_extract_entities)

    def execute(self, operation: str, **kwargs) -> ToolResult:
        """Execute tool operation"""
        if operation == 'classify_intent':
            return self._handle_classify_intent(**kwargs)
        elif operation == 'suggest_tool':
            return self._handle_suggest_tool(**kwargs)
        elif operation == 'extract_entities':
            return self._handle_extract_entities(**kwargs)
        raise ValueError(f"Unsupported operation: {operation}")

    def _handle_classify_intent(self, **kwargs):
        required_params = ['user_input']
        missing = [p for p in required_params if p not in kwargs or kwargs[p] in (None, "")]
        if missing:
            raise ValueError(f"Missing required parameters: {', '.join(missing)}")

        user_input = kwargs['user_input']
        cache_key = hash(user_input)
        
        if cache_key in self.cache:
            return self.cache[cache_key]

        if not self.services or not self.services.llm:
            raise RuntimeError("LLM service not available")

        prompt = f"""Classify this user input as either 'conversational' or 'actionable':

User input: "{user_input}"

Rules:
- 'conversational': Questions ABOUT the system, asking for suggestions, opinions, recommendations, explanations
- 'actionable': Direct commands to DO something with data (analyze, summarize, create, list, read, write)

Examples:
- "what tool should we add next?" -> conversational
- "analyze the sentiment of this text" -> actionable
- "can you suggest improvements?" -> conversational
- "summarize this document" -> actionable

Respond with ONLY: conversational OR actionable"""

        try:
            result = self.services.llm.generate(prompt, temperature=0.1, max_tokens=10).strip().lower()
            intent = 'conversational' if 'conversational' in result else 'actionable'
            confidence = 0.9
        except Exception as e:
            intent = 'conversational'
            confidence = 0.5

        result = {
            'intent': intent,
            'confidence': confidence,
            'requires_tool': intent == 'actionable',
            'user_input': user_input
        }

        self.cache[cache_key] = result
        return result

    def _handle_suggest_tool(self, **kwargs):
        required_params = ['user_input']
        missing = [p for p in required_params if p not in kwargs or kwargs[p] in (None, "")]
        if missing:
            raise ValueError(f"Missing required parameters: {', '.join(missing)}")

        user_input = kwargs['user_input'].lower()
        available_tools = kwargs.get('available_tools', [])

        # Simple keyword-based tool suggestion
        tool_keywords = {
            'FileOperationsTool': ['file', 'read', 'write', 'list', 'directory'],
            'HttpRequestTool': ['http', 'request', 'api', 'fetch', 'get', 'post'],
            'WebContentExtractor': ['web', 'scrape', 'extract', 'html', 'website'],
            'ContextSummarizerTool': ['summarize', 'sentiment', 'key points', 'analyze text']
        }

        suggested_tool = None
        max_matches = 0

        for tool_name, keywords in tool_keywords.items():
            matches = sum(1 for keyword in keywords if keyword in user_input)
            if matches > max_matches:
                max_matches = matches
                suggested_tool = tool_name

        return {
            'suggested_tool': suggested_tool,
            'confidence': min(max_matches * 0.3, 1.0),
            'available_tools': available_tools
        }

    def _handle_extract_entities(self, **kwargs):
        required_params = ['user_input']
        missing = [p for p in required_params if p not in kwargs or kwargs[p] in (None, "")]
        if missing:
            raise ValueError(f"Missing required parameters: {', '.join(missing)}")

        user_input = kwargs['user_input']

        if not self.services or not self.services.llm:
            # Fallback: simple extraction
            return {'entities': {}, 'raw_input': user_input}

        prompt = f"""Extract key entities from this user request. Return as JSON:
User input: {user_input}

Extract: action, target, parameters, context
Format: {{"action": "...", "target": "...", "parameters": {{}}, "context": "..."}}"""

        try:
            result = self.services.llm.generate(prompt, temperature=0.2, max_tokens=200)
            import json
            entities = json.loads(result)
            return {'entities': entities, 'raw_input': user_input}
        except Exception as e:
            return {'entities': {}, 'raw_input': user_input, 'error': str(e)}
