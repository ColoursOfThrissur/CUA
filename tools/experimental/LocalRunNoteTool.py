"""
LocalRunNoteTool - Auto-generated tool
"""
import json
from pathlib import Path
from datetime import datetime, timezone
from tools.tool_interface import BaseTool
from tools.tool_result import ToolResult, ResultStatus
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel

class LocalRunNoteTool(BaseTool):
    """Thin tool using orchestrator services for storage/time/IDs."""
    
    def __init__(self, orchestrator=None):
        self.description = "Auto-generated tool"
        self.services = orchestrator.get_services(self.__class__.__name__) if orchestrator else None
        super().__init__()

    def register_capabilities(self):
        """Register tool capabilities"""
        create_capability = ToolCapability(
            name='create',
            description='Create Operation',
            parameters=[
            Parameter(name='note_id', type=ParameterType.STRING, description='Parameter note_id', required=True),
            Parameter(name='text', type=ParameterType.STRING, description='Parameter text', required=True),
            Parameter(name='tags', type=ParameterType.LIST, description='Parameter tags', required=False),
            Parameter(name='status', type=ParameterType.STRING, description='Parameter status', required=False, default='active')
        ],
            returns="Operation result payload",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(create_capability, self._handle_create)

        get_capability = ToolCapability(
            name='get',
            description='Get Operation',
            parameters=[
            Parameter(name='note_id', type=ParameterType.STRING, description='Parameter note_id', required=True)
        ],
            returns="Operation result payload",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(get_capability, self._handle_get)

        list_capability = ToolCapability(
            name='list',
            description='List Operation',
            parameters=[
            Parameter(name='limit', type=ParameterType.INTEGER, description='Parameter limit', required=False, default=10)
        ],
            returns="Operation result payload",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(list_capability, self._handle_list)

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
        if operation == 'create':
            return self._handle_create(**parameters)
        elif operation == 'get':
            return self._handle_get(**parameters)
        elif operation == 'list':
            return self._handle_list(**parameters)
        return ToolResult(
            tool_name=self.name,
            capability_name=operation,
            status=ResultStatus.FAILURE,
            data=None,
            error_message=f"Unsupported operation: {operation}"
        )

    def _handle_create(self, **kwargs):
            note_id = kwargs.get('note_id')
            text = kwargs.get('text')
            tags = kwargs.get('tags', [])
            status = kwargs.get('status', 'active')

            if not note_id or not text:
                raise ValueError("Missing required parameters: note_id and text")

            if note_id == "":
                note_id = self.services.ids.generate()

            data = {
                "note_id": note_id,
                "text": text,
                "tags": tags,
                "status": status
            }

            return self.services.storage.save(note_id, data)

    def _handle_get(self, **kwargs):
            note_id = kwargs.get('note_id')
            if not note_id:
                raise ValueError("Missing required parameter: note_id")

            try:
                data = self.services.storage.get(note_id)
                return data
            except FileNotFoundError:
                raise FileNotFoundError(f"Note with ID '{note_id}' not found.")

    def _handle_list(self, **kwargs):
            limit = kwargs.get("limit", 10)
            if not isinstance(limit, int) or limit < 1 or limit > 50:
                raise ValueError("Invalid limit value. Must be an integer between 1 and 50.")

            return self.services.storage.list(limit=limit)
