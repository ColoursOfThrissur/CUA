"""
Tool Scaffolder - Create new tools from template (OPTIONAL FEATURE)
"""
from pathlib import Path

class ToolScaffolder:
    TEMPLATE = '''"""
{description}
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

class {class_name}(BaseTool):
    """STORAGE PATTERN: All data stored in data/{storage_dir}/ as JSON files"""
    
    def __init__(self, orchestrator=None, registry=None):
        self.name = "{tool_name}"
        self.description = "{description}"
        self.storage_dir = "data/{storage_dir}"
        Path(self.storage_dir).mkdir(parents=True, exist_ok=True)
        
        # Inter-tool communication: orchestrator and registry injection
        self.orchestrator = orchestrator
        self.registry = registry
        
        super().__init__()
    
    def register_capabilities(self):
        """Register tool capabilities"""
        cap = ToolCapability(
            name="execute",
            description="{description}",
            parameters=[],
            returns="Execution result payload",
            safety_level=SafetyLevel.MEDIUM,
            examples=[],
            dependencies=[]
        )
        self.add_capability(cap, self._execute)
        return list(self.get_capabilities().values())
    
    def execute(self, operation: str, **kwargs) -> ToolResult:
        """Execute tool operation - orchestrator-compatible signature"""
        if operation != "execute":
            return ToolResult(
                tool_name=self.name,
                capability_name=operation,
                status=ResultStatus.FAILURE,
                error_message=f"Unsupported operation: {{operation}}"
            )
        return self._execute(**kwargs)

    def _execute(self, **kwargs) -> ToolResult:
        """Execute tool operation"""
        try:
            # TODO: Implement tool logic
            return ToolResult(
                tool_name=self.name,
                capability_name="execute",
                status=ResultStatus.SUCCESS,
                data={{"message": "Not implemented"}}
            )
        except Exception as e:
            logger.error(f"Execution failed: {{e}}")
            return ToolResult(
                tool_name=self.name,
                capability_name="execute",
                status=ResultStatus.FAILURE,
                error_message=str(e)
            )
    
    # INTER-TOOL COMMUNICATION HELPERS
    def _call_tool(self, tool_name: str, operation: str, **params):
        """Call another tool via orchestrator - use this instead of reimplementing features"""
        if not self.orchestrator or not self.registry:
            raise RuntimeError("Tool not initialized with orchestrator/registry")
        
        tool = self.registry.get_tool_by_name(tool_name)
        if not tool:
            raise ValueError(f"Tool not found: {{tool_name}}")
        
        result = self.orchestrator.execute_tool_step(
            tool=tool,
            tool_name=tool_name,
            operation=operation,
            parameters=params
        )
        
        if not result.success:
            raise RuntimeError(f"Tool call failed: {{result.error}}")
        
        return result.data
    
    def _read_file(self, path: str) -> str:
        """Read file via FilesystemTool - ALWAYS use this instead of direct file I/O"""
        return self._call_tool("FilesystemTool", "read_file", path=path)
    
    def _write_file(self, path: str, content: str) -> str:
        """Write file via FilesystemTool - ALWAYS use this instead of direct file I/O"""
        return self._call_tool("FilesystemTool", "write_file", path=path, content=content)
    
    def _storage_path(self, item_id: str) -> Path:
        """Get consistent storage path for item - ALWAYS use this pattern"""
        safe_id = item_id.strip().replace("/", "_").replace("\\", "_")
        return Path(self.storage_dir) / f"{{safe_id}}.json"
'''
    
    def scaffold(self, tool_name: str, description: str, output_path: str, storage_dir: str = None) -> str:
        """Generate new tool from template"""
        class_name = ''.join(word.capitalize() for word in tool_name.split('_'))
        
        # Default storage directory based on tool name
        if not storage_dir:
            storage_dir = tool_name.lower().replace('tool', '').replace('_', '')
        
        code = self.TEMPLATE.format(
            tool_name=tool_name,
            class_name=class_name,
            description=description,
            storage_dir=storage_dir
        )
        
        Path(output_path).write_text(code, encoding='utf-8')
        return code
