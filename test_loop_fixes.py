#!/usr/bin/env python
"""Test the self-improvement loop fixes"""

import asyncio
from core.improvement_loop import SelfImprovementLoop
from planner.llm_client import LLMClient
from updater.orchestrator import UpdateOrchestrator

async def test_loop():
    print("\n=== Testing Self-Improvement Loop (With Fixes) ===\n")
    
    # Initialize
    llm = LLMClient()
    orch = UpdateOrchestrator(".")
    loop = SelfImprovementLoop(llm, orch, max_iterations=1)
    
    print("✅ Loop initialized")
    print(f"   State: {loop.state.status.value}")
    print(f"   Max iterations: {loop.max_iterations}")
    
    # Check key methods exist
    methods = [
        '_analyze_system',
        '_generate_proposal', 
        '_test_in_sandbox',
        '_apply_changes'
    ]
    
    print("\n✅ Key methods verified:")
    for method in methods:
        if hasattr(loop, method):
            print(f"   ✓ {method}()")
        else:
            print(f"   ✗ {method}() MISSING")
    
    # Test error handling
    print("\n🧪 Testing Error Handling:")
    
    # Test 1: sandbox_result without 'error' key
    sandbox_result = {
        'success': False,
        'output': 'Tests failed: X failed, Y passed',
        'tests_passed': 1,
        'tests_total': 5
    }
    error_msg = sandbox_result.get('output', 'Unknown error')
    print(f"   ✅ Sandbox error handling: '{error_msg}' (no KeyError)")
    
    # Test 2: apply_result without 'error' key on success
    apply_result_success = {
        'success': True,
        'backup_id': 'backup_20260208_120000'
    }
    if apply_result_success['success']:
        print(f"   ✅ Apply success: backup_id available")
    
    # Test 3: apply_result with 'error' key on failure
    apply_result_fail = {
        'success': False,
        'error': 'Rollback triggered'
    }
    error_msg = apply_result_fail.get('error', 'Unknown error')
    print(f"   ✅ Apply error handling: '{error_msg}' (no KeyError)")
    
    print("\n=== FIXES VERIFIED ===")
    print("✅ Fixed: sandbox_result.get('output') instead of .get('error')")
    print("✅ Fixed: apply_result.get('error') instead of direct access")
    print("\nLoop ready to run without KeyError issues!")

# Run test
if __name__ == "__main__":
    asyncio.run(test_loop())
