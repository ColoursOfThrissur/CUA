"""
Enhanced tool interface with capability-based design.
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Any
import time
from tools.tool_capability import ToolCapability
from tools.tool_result import ToolResult, ResultStatus

class BaseTool(ABC):
    """Base class for all tools with capability-based interface."""
    
    def __init__(self):
        self._capabilities: Dict[str, ToolCapability] = {}
        self._performance_stats: Dict[str, List[float]] = {}
        self.register_capabilities()
    
    @abstractmethod
    def register_capabilities(self):
        """Register all capabilities this tool provides."""
        pass
    
    def add_capability(self, capability: ToolCapability, handler_func):
        """Add a capability to this tool."""
        self._capabilities[capability.name] = capability
        setattr(self, f"_handle_{capability.name}", handler_func)
        self._performance_stats[capability.name] = []
    
    def get_capabilities(self) -> Dict[str, ToolCapability]:
        """Get all capabilities this tool provides."""
        return self._capabilities.copy()
    
    def has_capability(self, capability_name: str) -> bool:
        """Check if tool has a specific capability."""
        return capability_name in self._capabilities
    
    def execute_capability(self, capability_name: str, **kwargs) -> ToolResult:
        """Execute a specific capability."""
        if not self.has_capability(capability_name):
            return ToolResult(
                tool_name=self.__class__.__name__,
                capability_name=capability_name,
                status=ResultStatus.FAILURE,
                error_message=f"Capability '{capability_name}' not found"
            )
        
        start_time = time.time()
        try:
            handler = getattr(self, f"_handle_{capability_name}")
            result_data = handler(**kwargs)
            execution_time = time.time() - start_time
            
            # Track performance
            self._performance_stats[capability_name].append(execution_time)
            
            return ToolResult(
                tool_name=self.__class__.__name__,
                capability_name=capability_name,
                status=ResultStatus.SUCCESS,
                data=result_data,
                execution_time=execution_time
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            return ToolResult(
                tool_name=self.__class__.__name__,
                capability_name=capability_name,
                status=ResultStatus.FAILURE,
                error_message=str(e),
                execution_time=execution_time
            )
    
    def get_performance_stats(self, capability_name: str) -> Dict[str, float]:
        """Get performance statistics for a capability."""
        times = self._performance_stats.get(capability_name, [])
        if not times:
            return {"avg_time": 0.0, "success_rate": 0.0, "call_count": 0}
        
        return {
            "avg_time": sum(times) / len(times),
            "success_rate": 1.0,  # Will be enhanced with failure tracking
            "call_count": len(times)
        }
    
    def to_llm_description(self) -> str:
        """Generate LLM-friendly description of this tool."""
        tool_name = self.__class__.__name__
        capabilities_desc = []
        
        for cap_name, capability in self._capabilities.items():
            capabilities_desc.append(capability.to_llm_description())
        
        return f"""
Tool: {tool_name}
Capabilities:
{chr(10).join(capabilities_desc)}
        """.strip()