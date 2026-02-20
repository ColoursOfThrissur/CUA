"""
LocalCodeSnippetLibraryTool - Auto-generated tool
"""
import json
from pathlib import Path
from datetime import datetime, timezone
from tools.tool_interface import BaseTool
from tools.tool_result import ToolResult, ResultStatus
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel

class LocalCodeSnippetLibraryTool(BaseTool):
    """Thin tool using orchestrator services for storage/time/IDs."""
    
    def __init__(self, orchestrator=None):
        print(f"[TOOL_INIT] LocalCodeSnippetLibraryTool.__init__ called with orchestrator: {orchestrator}")
        self.description = "Auto-generated tool"
        self.services = orchestrator.get_services(self.__class__.__name__) if orchestrator else None
        print(f"[TOOL_INIT] Services set to: {self.services}")
        super().__init__()

    def register_capabilities(self):
        """Register tool capabilities"""
        save_snippet_capability = ToolCapability(
            name='save_snippet',
            description='Save_Snippet Operation',
            parameters=[
            Parameter(name='snippet_id', type=ParameterType.STRING, description='Parameter snippet_id', required=True),
            Parameter(name='language', type=ParameterType.STRING, description='Parameter language', required=True),
            Parameter(name='tags', type=ParameterType.LIST, description='Parameter tags', required=True),
            Parameter(name='description', type=ParameterType.STRING, description='Parameter description', required=True),
            Parameter(name='code_content', type=ParameterType.STRING, description='Parameter code_content', required=True),
            Parameter(name='version', type=ParameterType.INTEGER, description='Parameter version', required=True)
        ],
            returns="Operation result payload",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(save_snippet_capability, self._handle_save_snippet)

        get_snippet_capability = ToolCapability(
            name='get_snippet',
            description='Get_Snippet Operation',
            parameters=[
            Parameter(name='snippet_id', type=ParameterType.STRING, description='Parameter snippet_id', required=True)
        ],
            returns="Operation result payload",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(get_snippet_capability, self._handle_get_snippet)

        search_capability = ToolCapability(
            name='search',
            description='Search Operation',
            parameters=[
            Parameter(name='query', type=ParameterType.STRING, description='Parameter query', required=True),
            Parameter(name='language', type=ParameterType.STRING, description='Parameter language', required=False),
            Parameter(name='tags', type=ParameterType.LIST, description='Parameter tags', required=False)
        ],
            returns="Operation result payload",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(search_capability, self._handle_search)

        list_popular_capability = ToolCapability(
            name='list_popular',
            description='List_Popular Operation',
            parameters=[
            Parameter(name='limit', type=ParameterType.INTEGER, description='Parameter limit', required=False)
        ],
            returns="Operation result payload",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(list_popular_capability, self._handle_list_popular)

        update_version_capability = ToolCapability(
            name='update_version',
            description='Update_Version Operation',
            parameters=[
            Parameter(name='snippet_id', type=ParameterType.STRING, description='Parameter snippet_id', required=True),
            Parameter(name='new_code_content', type=ParameterType.STRING, description='Parameter new_code_content', required=True),
            Parameter(name='new_version', type=ParameterType.INTEGER, description='Parameter new_version', required=True)
        ],
            returns="Operation result payload",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(update_version_capability, self._handle_update_version)

    def execute(self, operation: str, **kwargs) -> ToolResult:
        """Execute tool operation"""
        parameters = kwargs
        if not isinstance(parameters, dict):
            return ToolResult(
                tool_name=self.name,
                capability_name=operation,
                status=ResultStatus.FAILURE,
                data=None,
                error_message="parameters must be a dict"
            )
        if operation == 'save_snippet':
            return self._handle_save_snippet(**parameters)
        elif operation == 'get_snippet':
            return self._handle_get_snippet(**parameters)
        elif operation == 'search':
            return self._handle_search(**parameters)
        elif operation == 'list_popular':
            return self._handle_list_popular(**parameters)
        elif operation == 'update_version':
            return self._handle_update_version(**parameters)
        return ToolResult(
            tool_name=self.name,
            capability_name=operation,
            status=ResultStatus.FAILURE,
            data=None,
            error_message=f"Unsupported operation: {operation}"
        )

    def _handle_save_snippet(self, **kwargs):
            snippet_id = kwargs.get('snippet_id')
            language = kwargs.get('language')
            tags = kwargs.get('tags')
            description = kwargs.get('description')
            code_content = kwargs.get('code_content')
            version = kwargs.get('version')

            data = {
                'snippet_id': snippet_id,
                'language': language,
                'tags': tags,
                'description': description,
                'code_content': code_content,
                'version': version
            }

            return self.services.storage.save(snippet_id, data)

    def _handle_get_snippet(self, **kwargs):
            snippet_id = kwargs.get('snippet_id')
            if not snippet_id:
                raise ValueError("Missing required parameter: snippet_id")

            return self.services.storage.get(snippet_id)

    def _handle_search(self, **kwargs):
            query = kwargs.get('query')
            language = kwargs.get('language')
            tags = kwargs.get('tags')

            if not query:
                raise ValueError("Missing required parameter: query")

            # TODO: Implement search logic using self.services
            return {}

    def _handle_list_popular(self, **kwargs):
            limit = kwargs.get("limit", 10)
            if not isinstance(limit, int) or limit <= 0:
                raise ValueError("Limit must be a positive integer.")

            return self.services.storage.list(limit=limit)

    def _handle_update_version(self, **kwargs):
            snippet_id = kwargs.get('snippet_id')
            new_code_content = kwargs.get('new_code_content')
            new_version = kwargs.get('new_version')

            if not all([snippet_id, new_code_content, new_version]):
                raise ValueError("Missing required parameters: snippet_id, new_code_content, new_version")

            existing_snippet = self.services.storage.get(snippet_id)
            if not existing_snippet:
                raise ValueError(f"Snippet with ID {snippet_id} does not exist")

            updated_snippet = {
                **existing_snippet,
                'code_content': new_code_content,
                'version': new_version
            }

            return self.services.storage.save(snippet_id, updated_snippet)
