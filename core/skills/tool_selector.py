from typing import Dict, List, Optional
from core.skills.execution_context import SkillExecutionContext, ToolVersion


class ContextAwareToolSelector:
    
    def __init__(self, tool_registry, circuit_breaker_manager=None):
        self.tool_registry = tool_registry
        self.circuit_breaker = circuit_breaker_manager
    
    def select_tools(self, context: SkillExecutionContext) -> SkillExecutionContext:
        available_tools = {}
        fallback_tools = []
        selected_tool = None
        reasoning = ""
        
        for tool_name in context.preferred_tools:
            tool = self.tool_registry.get_tool_by_name(tool_name)
            if not tool:
                context.warnings.append(f"Preferred tool {tool_name} not found in registry")
                continue
            
            cb_state = "CLOSED"
            healthy = True
            
            if self.circuit_breaker:
                cb_state = self.circuit_breaker.get_state(tool_name)
                healthy = (cb_state == "CLOSED")
            
            tool_version = ToolVersion(
                name=tool_name,
                version="v1",
                healthy=healthy,
                circuit_breaker_state=cb_state
            )
            
            available_tools[tool_name] = tool_version
            
            if healthy and not selected_tool:
                selected_tool = tool_name
                reasoning = f"{tool_name} is healthy, preferred by skill"
            elif not healthy:
                fallback_tools.append(tool_name)
        
        if not selected_tool and available_tools:
            selected_tool = list(available_tools.keys())[0]
            reasoning = f"Selected {selected_tool} (no healthy preferred tools)"
        
        context.selected_tool = selected_tool
        context.available_tools = available_tools
        context.fallback_tools = fallback_tools
        context.tool_selection_reasoning = reasoning
        
        return context
