"""Test code generator to see what's being generated"""
import sys
sys.path.append('.')

from pathlib import Path
from core.tool_evolution.code_generator import EvolutionCodeGenerator
from planner.llm_client import LLMClient
from tools.capability_registry import CapabilityRegistry

# Read BrowserAutomationTool
tool_file = Path('tools/experimental/BrowserAutomationTool.py')
current_code = tool_file.read_text()

print("Original code length:", len(current_code))
print("Has class definition:", "class BrowserAutomationTool" in current_code)

# Create mock proposal
proposal = {
    'action_type': 'add_capability',
    'description': 'Add form filling capability',
    'changes': ['Create handler', 'Register capability'],
    'confidence': 0.8
}

# Create code generator
registry = CapabilityRegistry()
llm_client = LLMClient(registry=registry)
code_gen = EvolutionCodeGenerator(llm_client)

# Test _extract_class_name
class_name = code_gen._extract_class_name(current_code)
print(f"\nExtracted class name: {class_name}")

# Test _extract_operation_name
op_name = code_gen._extract_operation_name(proposal['description'])
print(f"Extracted operation name: {op_name}")

print("\nIf code generator returns None, it means one of these failed:")
print("1. _extract_class_name returned None")
print("2. _generate_new_handler returned None (LLM failed)")
print("3. _insert_handler_before_execute returned code with same/less length")
print("4. _add_capability_registration returned code with same/less length")
print("5. _add_execute_routing returned code with same/less length")
