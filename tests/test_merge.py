"""
Test Multi-Step MODIFY Task with LLM Merge
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.incremental_code_builder import IncrementalCodeBuilder
from planner.llm_client import LLMClient
from tools.capability_registry import CapabilityRegistry

def test_multi_step_merge():
    """Test IncrementalCodeBuilder with multi-step LLM merge"""
    
    print("=" * 70)
    print("TESTING MULTI-STEP MERGE")
    print("=" * 70 + "\n")
    
    # Initialize LLM
    registry = CapabilityRegistry()
    llm_client = LLMClient(registry=registry)
    
    # Original code
    original_code = '''class HTTPTool:
    def __init__(self):
        self.name = "http_tool"
    
    def execute(self, operation, params):
        if operation == "get":
            return self._get(params.get("url"))
        return {"status": "error"}
'''
    
    print("Original code:")
    print(original_code)
    print()
    
    # Create builder with LLM
    builder = IncrementalCodeBuilder(original_code, llm_client)
    
    # Simulate step 1: Add error handling
    step1_code = '''class HTTPTool:
    def __init__(self):
        self.name = "http_tool"
    
    def execute(self, operation, params):
        if not operation:
            raise ValueError("Operation required")
        if operation == "get":
            return self._get(params.get("url"))
        return {"status": "error"}
'''
    
    builder.add_step("Add input validation", step1_code)
    print("[OK] Step 1 added: Add input validation")
    
    # Simulate step 2: Add logging
    step2_code = '''class HTTPTool:
    def __init__(self):
        self.name = "http_tool"
        self.logger = None
    
    def execute(self, operation, params):
        if self.logger:
            self.logger.info(f"Executing {operation}")
        if operation == "get":
            return self._get(params.get("url"))
        return {"status": "error"}
'''
    
    builder.add_step("Add logging support", step2_code)
    print("[OK] Step 2 added: Add logging support")
    
    # Merge all changes
    print("\n[INFO] Merging 2 steps using LLM...")
    merged_code = builder.merge_all_changes()
    
    if not merged_code:
        print("[FAIL] Merge failed")
        sys.exit(1)
    
    print("[OK] Merge completed\n")
    
    # Validate merged code
    print("Merged code:")
    print(merged_code)
    print()
    
    # Check that both changes are present
    assert "ValueError" in merged_code, "Missing validation from step 1"
    assert "logger" in merged_code, "Missing logger from step 2"
    
    print("[OK] Both step changes present in merged code")
    
    # Validate syntax
    try:
        import ast
        ast.parse(merged_code)
        print("[OK] Merged code has valid syntax")
    except SyntaxError as e:
        print(f"[FAIL] Syntax error: {e}")
        sys.exit(1)
    
    print("\n" + "=" * 70)
    print("[PASS] MULTI-STEP MERGE TEST PASSED")
    print("=" * 70)

if __name__ == "__main__":
    try:
        test_multi_step_merge()
    except AssertionError as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
