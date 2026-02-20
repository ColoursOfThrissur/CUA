"""
Enhanced context provider for tool generation - fixes LLM context gaps
"""
from typing import Dict, List, Any
from pathlib import Path


class ToolGenerationContext:
    """Provides rich context to LLM during tool generation to prevent common errors"""
    
    @staticmethod
    def get_storage_patterns() -> str:
        """Standard storage patterns for generated tools"""
        return """
STORAGE PATTERNS (MANDATORY):
1. All data MUST be stored in: data/{tool_specific_dir}/
2. Use consistent path pattern across ALL methods:
   - _handle_create writes to: data/{dir}/{id}.json
   - _handle_get reads from: data/{dir}/{id}.json  
   - _handle_list scans: data/{dir}/*.json
3. ALWAYS create directories before writing:
   Path(self.storage_dir).mkdir(parents=True, exist_ok=True)
4. Use _storage_path() helper for consistency:
   def _storage_path(self, item_id: str) -> Path:
       return Path(self.storage_dir) / f"{item_id}.json"

EXAMPLE (LocalRunNoteTool):
- Storage dir: data/run_notes/
- Create: writes data/run_notes/{note_id}.json
- Get: reads data/run_notes/{note_id}.json
- List: scans data/run_notes/*.json
"""

    @staticmethod
    def get_required_imports() -> str:
        """Required imports for all generated tools"""
        return """
REQUIRED IMPORTS:
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from tools.tool_interface import BaseTool
from tools.tool_result import ToolResult, ResultStatus
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel

logger = logging.getLogger(__name__)
"""

    @staticmethod
    def get_data_structure_template(tool_spec: Dict[str, Any]) -> str:
        """Generate data structure specification from tool spec"""
        operations = tool_spec.get('inputs', [])
        
        # Extract fields from create operation
        create_fields = []
        for op in operations:
            if isinstance(op, dict) and op.get('operation') == 'create':
                params = op.get('parameters', [])
                for p in params:
                    if isinstance(p, dict):
                        name = p.get('name')
                        ptype = p.get('type', 'string')
                        if name:
                            create_fields.append(f"  - {name}: {ptype}")
        
        fields_text = "\n".join(create_fields) if create_fields else "  - id: string\n  - data: string"
        
        return f"""
DATA STRUCTURE:
{{
{fields_text}
  - timestamp_utc: string (ISO format)
}}

STORAGE FORMAT: JSON files in data/{tool_spec.get('name', 'tool').lower().replace('tool', '')}/
"""

    @staticmethod
    def get_method_context(method_name: str, previous_methods: Dict[str, str]) -> str:
        """Provide context about what previous methods wrote"""
        context = f"\nCONTEXT FOR {method_name}:\n"
        
        if method_name == "_handle_get" and "_handle_create" in previous_methods:
            context += """
- _handle_create already wrote data to storage
- You MUST read from the SAME path pattern that _handle_create used
- Extract the storage path logic from _handle_create and use it here
- Example: If create writes to Path(self.storage_dir) / f"{id}.json"
          Then get MUST read from Path(self.storage_dir) / f"{id}.json"
"""
        
        elif method_name == "_handle_list" and "_handle_create" in previous_methods:
            context += """
- _handle_create already wrote data to storage
- You MUST scan the SAME directory that _handle_create used
- Use Path(self.storage_dir).glob("*.json") to find all files
- Read and parse each JSON file, sort by timestamp
- Return actual persisted data, NOT mock/hardcoded records
"""
        
        return context

    @staticmethod
    def get_inter_tool_communication_guide() -> str:
        """Guide for using orchestrator to call other tools"""
        return """
INTER-TOOL COMMUNICATION:
Your tool has access to orchestrator and registry for calling other tools.

WHEN TO USE OTHER TOOLS:
- Need to read/write files? Use FilesystemTool via self._read_file() / self._write_file()
- Need HTTP requests? Use HTTPTool via self._call_tool("HTTPTool", "get", url=...)
- Need JSON parsing? Use JSONTool via self._call_tool("JSONTool", "parse", ...)

HELPER METHODS (already in scaffold):
1. self._call_tool(tool_name, operation, **params)
   - Calls another tool via orchestrator
   - Raises RuntimeError if tool not found or call fails
   - Returns result data on success

2. self._read_file(path: str) -> str
   - Reads file via FilesystemTool (respects security sandbox)
   - Use this INSTEAD of open(path, 'r')

3. self._write_file(path: str, content: str) -> str
   - Writes file via FilesystemTool (respects security sandbox)
   - Use this INSTEAD of open(path, 'w')

EXAMPLE - Reading config file:
try:
    config_data = self._read_file("config/settings.json")
    config = json.loads(config_data)
except Exception as e:
    return ToolResult(
        tool_name=self.name,
        capability_name="execute",
        status=ResultStatus.FAILURE,
        error_message=f"Failed to read config: {e}"
    )

EXAMPLE - Fetching URL:
try:
    response = self._call_tool("HTTPTool", "get", url="https://api.example.com/data")
    data = json.loads(response.get('body', '{}'))
except Exception as e:
    return ToolResult(
        tool_name=self.name,
        capability_name="execute",
        status=ResultStatus.FAILURE,
        error_message=f"Failed to fetch data: {e}"
    )

IMPORTANT:
- ALWAYS use helper methods instead of direct file I/O
- This ensures security validation and proper error handling
- Tools can be composed without reimplementing features
"""

    @staticmethod
    def get_orchestrator_compatible_signature() -> str:
        """Explain orchestrator-compatible method signatures"""
        return """
ORCHESTRATOR-COMPATIBLE SIGNATURES:

1. execute() method MUST accept **kwargs:
   def execute(self, operation: str, **kwargs) -> ToolResult:
       # Dispatch to handlers
       if operation == "create":
           return self._handle_create(**kwargs)
       ...

2. Handler methods MUST accept **kwargs:
   def _handle_create(self, **kwargs) -> ToolResult:
       # Extract parameters
       note_id = kwargs.get('note_id')
       notes = kwargs.get('notes')
       ...

3. DO NOT use (self, params: dict) signature - orchestrator passes **kwargs

4. Parameter validation pattern:
   def _handle_create(self, **kwargs) -> ToolResult:
       # Validate required params
       note_id = kwargs.get('note_id')
       if not note_id or not isinstance(note_id, str):
           return ToolResult(
               tool_name=self.name,
               capability_name="create",
               status=ResultStatus.FAILURE,
               error_message="note_id is required and must be a string"
           )
       ...
"""

    @staticmethod
    def get_complete_example() -> str:
        """Complete working example of a well-formed tool"""
        return '''
COMPLETE EXAMPLE (LocalRunNoteTool):

"""
LocalRunNoteTool - Manages local run notes
"""
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from tools.tool_interface import BaseTool
from tools.tool_result import ToolResult, ResultStatus
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel

logger = logging.getLogger(__name__)

class LocalRunNoteTool(BaseTool):
    """STORAGE PATTERN: All data stored in data/run_notes/ as JSON files"""
    
    def __init__(self, orchestrator=None, registry=None):
        self.name = "LocalRunNoteTool"
        self.description = "Manage local run notes"
        self.storage_dir = "data/run_notes"
        Path(self.storage_dir).mkdir(parents=True, exist_ok=True)
        
        # Inter-tool communication
        self.orchestrator = orchestrator
        self.registry = registry
        
        super().__init__()
    
    def register_capabilities(self):
        create_cap = ToolCapability(
            name="create",
            description="Create a run note",
            parameters=[
                Parameter(name="note_id", type=ParameterType.STRING, description="Unique note ID", required=True),
                Parameter(name="notes", type=ParameterType.STRING, description="Note content", required=True),
                Parameter(name="tags", type=ParameterType.LIST, description="Tags", required=False, default=None)
            ],
            returns="Created note data",
            safety_level=SafetyLevel.LOW,
            examples=[{"note_id": "run-001", "notes": "baseline test", "tags": ["smoke"]}],
            dependencies=[]
        )
        self.add_capability(create_cap, self._handle_create)
        
        get_cap = ToolCapability(
            name="get",
            description="Get a run note by ID",
            parameters=[
                Parameter(name="note_id", type=ParameterType.STRING, description="Note ID", required=True)
            ],
            returns="Note data",
            safety_level=SafetyLevel.LOW,
            examples=[{"note_id": "run-001"}],
            dependencies=[]
        )
        self.add_capability(get_cap, self._handle_get)
        
        list_cap = ToolCapability(
            name="list",
            description="List recent notes",
            parameters=[
                Parameter(name="limit", type=ParameterType.INTEGER, description="Max notes", required=False, default=10)
            ],
            returns="List of notes",
            safety_level=SafetyLevel.LOW,
            examples=[{"limit": 5}],
            dependencies=[]
        )
        self.add_capability(list_cap, self._handle_list)
    
    def execute(self, operation: str, **kwargs) -> ToolResult:
        if operation == "create":
            return self._handle_create(**kwargs)
        elif operation == "get":
            return self._handle_get(**kwargs)
        elif operation == "list":
            return self._handle_list(**kwargs)
        return ToolResult(
            tool_name=self.name,
            capability_name=operation,
            status=ResultStatus.FAILURE,
            error_message=f"Unsupported operation: {operation}"
        )
    
    def _storage_path(self, note_id: str) -> Path:
        """CONSISTENT storage path - used by ALL methods"""
        safe_id = note_id.strip().replace("/", "_").replace("\\\\", "_")
        return Path(self.storage_dir) / f"{safe_id}.json"
    
    def _handle_create(self, **kwargs) -> ToolResult:
        note_id = kwargs.get('note_id')
        notes = kwargs.get('notes')
        tags = kwargs.get('tags') or []
        
        if not note_id or not isinstance(note_id, str):
            return ToolResult(
                tool_name=self.name,
                capability_name="create",
                status=ResultStatus.FAILURE,
                error_message="note_id is required and must be a string"
            )
        
        if not notes or not isinstance(notes, str):
            return ToolResult(
                tool_name=self.name,
                capability_name="create",
                status=ResultStatus.FAILURE,
                error_message="notes is required and must be a string"
            )
        
        note_data = {
            "note_id": note_id,
            "notes": notes,
            "tags": tags,
            "timestamp_utc": datetime.now(timezone.utc).isoformat()
        }
        
        path = self._storage_path(note_id)
        path.write_text(json.dumps(note_data, indent=2), encoding='utf-8')
        
        return ToolResult(
            tool_name=self.name,
            capability_name="create",
            status=ResultStatus.SUCCESS,
            data=note_data
        )
    
    def _handle_get(self, **kwargs) -> ToolResult:
        note_id = kwargs.get('note_id')
        
        if not note_id or not isinstance(note_id, str):
            return ToolResult(
                tool_name=self.name,
                capability_name="get",
                status=ResultStatus.FAILURE,
                error_message="note_id is required"
            )
        
        path = self._storage_path(note_id)
        if not path.exists():
            return ToolResult(
                tool_name=self.name,
                capability_name="get",
                status=ResultStatus.FAILURE,
                error_message=f"Note not found: {note_id}"
            )
        
        data = json.loads(path.read_text(encoding='utf-8'))
        return ToolResult(
            tool_name=self.name,
            capability_name="get",
            status=ResultStatus.SUCCESS,
            data=data
        )
    
    def _handle_list(self, **kwargs) -> ToolResult:
        limit = kwargs.get('limit', 10)
        
        if not isinstance(limit, int) or limit < 1:
            return ToolResult(
                tool_name=self.name,
                capability_name="list",
                status=ResultStatus.FAILURE,
                error_message="limit must be a positive integer"
            )
        
        items = []
        for path in Path(self.storage_dir).glob("*.json"):
            try:
                items.append(json.loads(path.read_text(encoding='utf-8')))
            except Exception:
                continue
        
        items.sort(key=lambda x: x.get('timestamp_utc', ''), reverse=True)
        return ToolResult(
            tool_name=self.name,
            capability_name="list",
            status=ResultStatus.SUCCESS,
            data=items[:limit]
        )
    
    # INTER-TOOL COMMUNICATION HELPERS
    def _call_tool(self, tool_name: str, operation: str, **params):
        """Call another tool via orchestrator"""
        if not self.orchestrator or not self.registry:
            raise RuntimeError("Tool not initialized with orchestrator/registry")
        
        tool = self.registry.get_tool_by_name(tool_name)
        if not tool:
            raise ValueError(f"Tool not found: {tool_name}")
        
        result = self.orchestrator.execute_tool_step(
            tool=tool,
            tool_name=tool_name,
            operation=operation,
            parameters=params
        )
        
        if not result.success:
            raise RuntimeError(f"Tool call failed: {result.error}")
        
        return result.data
    
    def _read_file(self, path: str) -> str:
        """Read file via FilesystemTool"""
        return self._call_tool("FilesystemTool", "read_file", path=path)
    
    def _write_file(self, path: str, content: str) -> str:
        """Write file via FilesystemTool"""
        return self._call_tool("FilesystemTool", "write_file", path=path, content=content)
'''

    @classmethod
    def build_enhanced_prompt(cls, base_prompt: str, tool_spec: Dict[str, Any], 
                             stage: str = "full", previous_methods: Dict[str, str] = None) -> str:
        """Build enhanced prompt with rich context"""
        
        enhanced = base_prompt + "\n\n"
        enhanced += "=" * 80 + "\n"
        enhanced += "CRITICAL CONTEXT TO PREVENT COMMON ERRORS:\n"
        enhanced += "=" * 80 + "\n\n"
        
        enhanced += cls.get_required_imports() + "\n"
        enhanced += cls.get_storage_patterns() + "\n"
        enhanced += cls.get_data_structure_template(tool_spec) + "\n"
        enhanced += cls.get_orchestrator_compatible_signature() + "\n"
        enhanced += cls.get_inter_tool_communication_guide() + "\n"
        
        if stage == "method" and previous_methods:
            method_name = base_prompt.split("Target method:")[-1].split("\n")[0].strip() if "Target method:" in base_prompt else ""
            if method_name:
                enhanced += cls.get_method_context(method_name, previous_methods) + "\n"
        
        enhanced += "\n" + "=" * 80 + "\n"
        enhanced += "COMPLETE WORKING EXAMPLE:\n"
        enhanced += "=" * 80 + "\n"
        enhanced += cls.get_complete_example() + "\n"
        
        return enhanced
