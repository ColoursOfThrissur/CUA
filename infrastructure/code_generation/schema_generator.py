"""Dynamic schema generation from capability registry"""
from enum import Enum
from typing import Dict, List, Any
from pydantic import BaseModel, Field, create_model

def generate_dynamic_schema(registry):
    """Generate Pydantic schema from registered tools"""
    
    # Get all registered tools and capabilities
    tools = {}
    operations = {}
    
    for tool in registry.tools:
        tool_name = tool.__class__.__name__.lower().replace('tool', '') + '_tool'
        tools[tool_name] = tool
        
        for cap_name in tool.get_capabilities().keys():
            if tool_name not in operations:
                operations[tool_name] = []
            operations[tool_name].append(cap_name)
    
    # Create dynamic enums
    ToolName = Enum('ToolName', {name.upper(): name for name in tools.keys()})
    
    all_operations = {}
    for tool_ops in operations.values():
        for op in tool_ops:
            all_operations[op.upper()] = op
    OperationName = Enum('OperationName', all_operations)
    
    return ToolName, OperationName, tools, operations

def get_tool_descriptions(registry) -> str:
    """Generate tool descriptions for LLM prompt"""
    descriptions = []
    
    for tool in registry.tools:
        tool_name = tool.__class__.__name__
        capabilities = tool.get_capabilities()
        
        descriptions.append(f"\n{tool_name}:")
        for cap_name, capability in capabilities.items():
            params = ", ".join([f"{p.name}: {p.type.value}" for p in capability.parameters])
            descriptions.append(f"  - {cap_name}({params}): {capability.description}")
    
    return "\n".join(descriptions)

def get_tool_descriptions(registry) -> str:
    """Generate tool descriptions for LLM prompt"""
    descriptions = []
    
    for tool in registry.tools:
        tool_name = tool.__class__.__name__
        capabilities = tool.get_capabilities()
        
        descriptions.append(f"\n{tool_name}:")
        for cap_name, capability in capabilities.items():
            params = ", ".join([f"{p.name}: {p.type.value}" for p in capability.parameters])
            descriptions.append(f"  - {cap_name}({params}): {capability.description}")
    
    return "\n".join(descriptions)

def validate_plan_against_registry(plan_data: Dict, registry) -> tuple[bool, str]:
    """Validate plan uses only registered tools/operations"""
    
    available_tools = {tool.__class__.__name__.lower().replace('tool', '') + '_tool' 
                      for tool in registry.tools}
    
    available_ops = set()
    for tool in registry.tools:
        available_ops.update(tool.get_capabilities().keys())
    
    for step in plan_data.get('steps', []):
        tool = step.get('tool', '')
        operation = step.get('operation', '')
        
        if tool not in available_tools:
            return False, f"Unknown tool: {tool}. Available: {available_tools}"
        
        if operation not in available_ops:
            return False, f"Unknown operation: {operation}. Available: {available_ops}"
    
    return True, "Valid"
