"""
JSON Tool - Parse and manipulate JSON data
"""
import json
from tools.tool_interface import BaseTool
from tools.tool_result import ToolResult, ResultStatus

class JSONTool(BaseTool):

    def __init__(self):
        self.name = 'json_tool'
        self.description = 'Parse and manipulate JSON'
        self.capabilities = ['parse', 'stringify', 'query']
        super().__init__()

    def register_capabilities(self):
        """Register JSON manipulation capabilities"""
        from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel
        parse_cap = ToolCapability(name='parse', description='Parse JSON string', parameters=[Parameter('text', ParameterType.STRING, 'JSON string to parse')], returns='Parsed JSON object', safety_level=SafetyLevel.LOW, examples=[{'text': '{"key": "value"}'}])
        self.add_capability(parse_cap, self._parse)
        stringify_cap = ToolCapability(name='stringify', description='Convert object to JSON string', parameters=[Parameter('data', ParameterType.DICT, 'Data to stringify')], returns='JSON string', safety_level=SafetyLevel.LOW, examples=[{'data': {'key': 'value'}}])
        self.add_capability(stringify_cap, self._stringify)
        query_cap = ToolCapability(name='query', description='Query JSON data by path', parameters=[Parameter('data', ParameterType.DICT, 'JSON data'), Parameter('path', ParameterType.STRING, 'Dot-separated path')], returns='Queried value', safety_level=SafetyLevel.LOW, examples=[{'data': {'user': {'name': 'Alice'}}, 'path': 'user.name'}])
        self.add_capability(query_cap, self._query)

    def execute(self, operation: str, parameters: dict) -> ToolResult:
        if operation == 'parse':
            return self._parse(parameters)
        elif operation == 'stringify':
            return self._stringify(parameters)
        elif operation == 'query':
            return self._query(parameters)
        return ToolResult(tool_name=self.name, capability_name=operation, status=ResultStatus.FAILURE, error_message='Unknown operation')

    def _parse(self, params: dict) -> ToolResult:
        text = params.get('text')
        if not text:
            return self._create_tool_result(capability_name='parse', status=ResultStatus.FAILURE, error_message='Text required')
        try:
            data = json.loads(text)
            return self._create_tool_result(capability_name='parse', status=ResultStatus.SUCCESS, data=data)
        except json.JSONDecodeError as e:
            return self._create_tool_result(capability_name='parse', status=ResultStatus.FAILURE, error_message=f'Invalid JSON: {str(e)}')

    def _stringify(self, params: dict) -> ToolResult:
        data = params.get('data')
        if data is None:
            return self._create_tool_result(capability_name='stringify', status=ResultStatus.FAILURE, error_message='Data required')
        try:
            text = json.dumps(data, indent=2)
            return self._create_tool_result(capability_name='stringify', status=ResultStatus.SUCCESS, data=text)
        except (TypeError, OverflowError) as e:
            return self._create_tool_result(capability_name='stringify', status=ResultStatus.FAILURE, error_message=f'Invalid JSON input: {str(e)}')

    def _query(self, params: dict) -> ToolResult:
        data = params.get('data')
        path = params.get('path', '')
        if data is None:
            return ToolResult(tool_name=self.name, capability_name='query', status=ResultStatus.FAILURE, error_message='Data required')
        try:
            result = data
            for key in path.split('.'):
                if key:
                    result = result[key]
            return ToolResult(tool_name=self.name, capability_name='query', status=ResultStatus.SUCCESS, data=result)
        except (KeyError, TypeError) as e:
            return ToolResult(tool_name=self.name, capability_name='query', status=ResultStatus.FAILURE, error_message=f'Query failed: {str(e)}')

    def _create_tool_result(self, capability_name: str, status: ResultStatus, data=None, error_message=None) -> ToolResult:
        return ToolResult(tool_name=self.name, capability_name=capability_name, status=status, data=data, error_message=error_message)