"""
Standardized tool result format for consistent feedback and learning.
"""
from dataclasses import dataclass
from typing import Any, Dict, Optional
from datetime import datetime
from enum import Enum

class ResultStatus(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"

@dataclass
class ToolResult:
    tool_name: str
    capability_name: str
    status: ResultStatus
    data: Any = None
    error_message: Optional[str] = None
    execution_time: float = 0.0
    timestamp: datetime = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.metadata is None:
            self.metadata = {}
    
    def is_success(self) -> bool:
        return self.status == ResultStatus.SUCCESS
    
    def is_failure(self) -> bool:
        return self.status == ResultStatus.FAILURE
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "capability_name": self.capability_name,
            "status": self.status.value,
            "data": self.data,
            "error_message": self.error_message,
            "execution_time": self.execution_time,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }
    
    def to_llm_feedback(self) -> str:
        """Convert result to LLM-friendly feedback."""
        if self.is_success():
            return f"+ {self.tool_name}.{self.capability_name} succeeded: {self.data}"
        else:
            return f"- {self.tool_name}.{self.capability_name} failed: {self.error_message}"