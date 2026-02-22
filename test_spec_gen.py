"""Test spec generator with browser automation tool"""
import sys
sys.path.insert(0, '.')

from core.tool_creation.spec_generator import SpecGenerator
from planner.llm_client import LLMClient

# Create instances
llm_client = LLMClient()
spec_gen = SpecGenerator(capability_graph=None)

# Test description
description = """Create a browser automation tool with these operations:
1. open_and_navigate - Opens browser and navigates to URL (needs url parameter)
2. get_page_content - Returns current page text (NO parameters, uses current page)
3. take_screenshot - Takes screenshot (needs filename parameter)
4. close - Closes browser (NO parameters)

Use self.services.browser for all operations."""

print("Generating spec...")
spec = spec_gen.propose_tool_spec(description, llm_client)

if spec:
    print("\nSpec generated successfully!")
    print(f"Tool name: {spec['name']}")
    print(f"Confidence: {spec.get('confidence', 0):.2f}")
    print(f"\nOperations:")
    for inp in spec.get('inputs', []):
        op = inp.get('operation')
        params = inp.get('parameters', [])
        if params:
            param_names = [p['name'] for p in params]
            print(f"  - {op}: {param_names}")
        else:
            print(f"  - {op}: (no parameters)")
    
    # Check if get_page_content has no parameters
    get_page_op = next((inp for inp in spec.get('inputs', []) if inp.get('operation') == 'get_page_content'), None)
    if get_page_op:
        params = get_page_op.get('parameters', [])
        if not params:
            print("\nTEST PASSED: get_page_content has no parameters (correct!)")
        else:
            print(f"\nTEST FAILED: get_page_content has parameters: {[p['name'] for p in params]}")
    else:
        print("\nTEST FAILED: get_page_content operation not found")
else:
    print("Failed to generate spec")
