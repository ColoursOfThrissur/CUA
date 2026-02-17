"""
Tool capability metadata system for dynamic tool discovery.
"""
from dataclasses import dataclass
from typing import Dict, List, Any, Optional
from enum import Enum

class SafetyLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class ParameterType(Enum):
    STRING = "string"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    LIST = "list"
    DICT = "dict"
    FILE_PATH = "file_path"

@dataclass
class Parameter:
    name: str
    type: ParameterType
    description: str
    required: bool = True
    default: Any = None

@dataclass
class ToolCapability:
    name: str
    description: str
    parameters: List[Parameter]
    returns: str
    safety_level: SafetyLevel
    examples: List[Dict[str, Any]]
    dependencies: List[str] = None
    
    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []
    
    def to_llm_description(self) -> str:
        """Convert capability to LLM-friendly description."""
        param_desc = []
        for param in self.parameters:
            req = "required" if param.required else "optional"
            param_desc.append(f"  - {param.name} ({param.type.value}, {req}): {param.description}")
        
        params_str = "\n".join(param_desc) if param_desc else "  No parameters"
        
        examples_str = ""
        if self.examples:
            examples_str = "\nExamples:\n" + "\n".join([f"  {ex}" for ex in self.examples])
        
        return f"""
Capability: {self.name}
Description: {self.description}
Parameters:
{params_str}
Returns: {self.returns}
Safety Level: {self.safety_level.value}
{examples_str}
        """.strip()