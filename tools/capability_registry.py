"""
Dynamic capability registry for tool discovery and management.
"""
from typing import Dict, List, Optional, Set
from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, SafetyLevel
from tools.tool_result import ToolResult, ResultStatus

class CapabilityRegistry:
    """Central registry for all tool capabilities."""
    
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._capabilities: Dict[str, ToolCapability] = {}
        self._tool_by_capability: Dict[str, str] = {}
        self._performance_history: Dict[str, List[ToolResult]] = {}
        self._orchestrator = None
    
    def register_tool(self, tool: BaseTool):
        """Register a tool and its capabilities."""
        tool_name = tool.__class__.__name__
        
        # Unregister old instance if exists (for hot-reload)
        if tool_name in self._tools:
            self.unregister_tool(tool_name)
        
        self._tools[tool_name] = tool
        
        # Register all capabilities
        for cap_name, capability in tool.get_capabilities().items():
            self._capabilities[cap_name] = capability
            self._tool_by_capability[cap_name] = tool_name
            self._performance_history[cap_name] = []

    def unregister_tool(self, tool_name: str) -> bool:
        """Unregister a tool and all of its capabilities."""
        if tool_name not in self._tools:
            return False

        # Remove capability mappings owned by this tool.
        owned_capabilities = [
            cap_name for cap_name, mapped_tool in self._tool_by_capability.items()
            if mapped_tool == tool_name
        ]
        for cap_name in owned_capabilities:
            self._tool_by_capability.pop(cap_name, None)
            self._capabilities.pop(cap_name, None)
            self._performance_history.pop(cap_name, None)

        self._tools.pop(tool_name, None)
        return True
    
    def get_all_capabilities(self) -> Dict[str, ToolCapability]:
        """Get all registered capabilities."""
        return self._capabilities.copy()
    
    def get_capabilities_by_safety_level(self, max_level: SafetyLevel) -> Dict[str, ToolCapability]:
        """Get capabilities filtered by safety level."""
        safety_order = [SafetyLevel.LOW, SafetyLevel.MEDIUM, SafetyLevel.HIGH, SafetyLevel.CRITICAL]
        max_index = safety_order.index(max_level)
        
        filtered = {}
        for cap_name, capability in self._capabilities.items():
            if safety_order.index(capability.safety_level) <= max_index:
                filtered[cap_name] = capability
        
        return filtered
    
    def find_capabilities_for_task(self, task_description: str) -> List[str]:
        """Find relevant capabilities for a task description."""
        # Simple keyword matching - can be enhanced with embeddings later
        relevant_caps = []
        task_lower = task_description.lower()
        for cap_name, capability in self._capabilities.items():
            # Build a list of candidate keywords: capability name + description words
            keywords = [cap_name.lower()] + capability.description.lower().split()
            if any(keyword in task_lower for keyword in keywords):
                relevant_caps.append(cap_name)
        
        return relevant_caps
    
    def execute_capability(self, capability_name: str, **kwargs) -> ToolResult:
        """Execute a capability by name."""
        import time
        
        if capability_name not in self._tool_by_capability:
            return ToolResult(
                tool_name="Registry",
                capability_name=capability_name,
                status=ResultStatus.FAILURE,
                error_message=f"Capability '{capability_name}' not found"
            )
        
        tool_name = self._tool_by_capability[capability_name]
        tool = self._tools[tool_name]
        
        start_time = time.time()

        # Use the orchestrator for compatibility across mixed tool execute signatures
        # (some tools expect params dict; some expect kwargs; some use BaseTool.execute_capability).
        if self._orchestrator is None:
            from core.tool_orchestrator import ToolOrchestrator
            self._orchestrator = ToolOrchestrator(registry=self)

        orchestration = self._orchestrator.execute_tool_step(
            tool=tool,
            tool_name=tool_name,
            operation=capability_name,
            parameters=kwargs,
            context={},
        )

        execution_time = time.time() - start_time
        result = ToolResult(
            tool_name=tool_name,
            capability_name=capability_name,
            status=ResultStatus.SUCCESS if orchestration.success else ResultStatus.FAILURE,
            data=orchestration.data,
            error_message=orchestration.error,
            execution_time=execution_time,
        )

        self._performance_history[capability_name].append(result)
        return result
    
    def get_capability_performance(self, capability_name: str) -> Dict:
        """Get performance statistics for a capability."""
        history = self._performance_history.get(capability_name, [])
        if not history:
            return {"success_rate": 0.0, "avg_time": 0.0, "total_calls": 0}
        
        successes = sum(1 for r in history if r.is_success())
        total_time = sum(r.execution_time for r in history)
        
        return {
            "success_rate": successes / len(history),
            "avg_time": total_time / len(history),
            "total_calls": len(history),
            "recent_failures": [r.error_message for r in history[-5:] if r.is_failure()]
        }
    
    def to_llm_context(self, max_safety_level: SafetyLevel = SafetyLevel.MEDIUM) -> str:
        """Generate LLM context with available capabilities."""
        capabilities = self.get_capabilities_by_safety_level(max_safety_level)
        
        context_parts = ["Available capabilities:"]
        for cap_name, capability in capabilities.items():
            perf = self.get_capability_performance(cap_name)
            success_rate = f"({perf['success_rate']:.1%} success)" if perf['total_calls'] > 0 else "(new)"
            
            context_parts.append(f"- {cap_name}: {capability.description} {success_rate}")
        
        return "\n".join(context_parts)

    @property
    def tools(self):
        """Get all registered tools."""
        return list(self._tools.values())
    
    def get_tool_by_name(self, tool_name: str):
        """Get tool by name - always returns current registered instance."""
        # Direct lookup
        if tool_name in self._tools:
            return self._tools[tool_name]
        
        # Try with Tool suffix
        if f"{tool_name}Tool" in self._tools:
            return self._tools[f"{tool_name}Tool"]
        
        # Try without _tool suffix
        clean_name = tool_name.replace("_tool", "")
        for name, tool in self._tools.items():
            if name.lower().replace("tool", "") == clean_name:
                return tool
        
        # Last resort: check if any tool's .name attribute matches
        for tool in self._tools.values():
            if hasattr(tool, 'name') and tool.name == tool_name:
                return tool
        
        return None

# Global registry instance
registry = CapabilityRegistry()
