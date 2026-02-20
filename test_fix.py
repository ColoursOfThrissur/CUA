#!/usr/bin/env python3
"""Test the tool creation fix"""
import sys
sys.path.insert(0, '.')

from core.tool_creation_flow import ToolCreationFlow
from core.capability_graph import CapabilityGraph
from core.expansion_mode import ExpansionMode
from core.growth_budget import GrowthBudget
from planner.llm_client import LLMClient

# Initialize
capability_graph = CapabilityGraph()
expansion_mode = ExpansionMode(enabled=True)
budget = GrowthBudget()
tool_creation = ToolCreationFlow(capability_graph, expansion_mode, budget)

# Create LLM client
llm_client = LLMClient()

# Test
print("Testing tool creation...")
success, msg = tool_creation.create_new_tool(
    "Simple test tool",
    llm_client,
    bypass_budget=True,
    preferred_tool_name="TestToolFix",
)

print(f"Success: {success}")
print(f"Message: {msg}")
