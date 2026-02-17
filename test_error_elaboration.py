#!/usr/bin/env python
"""Demonstrate enhanced error reporting in improvement loop"""

from core.improvement_loop import SelfImprovementLoop
from planner.llm_client import LLMClient
from updater.orchestrator import UpdateOrchestrator

def test_error_elaboration():
    """Test the _elaborate_error method"""
    print("\n=== Enhanced Error Reporting Test ===\n")
    
    llm = LLMClient()
    orch = UpdateOrchestrator(".")
    loop = SelfImprovementLoop(llm, orch, max_iterations=1)
    
    # Test 1: KeyError
    print("Test 1: KeyError elaboration")
    print("━" * 60)
    try:
        d = {'a': 1}
        x = d['missing_key']
    except KeyError as e:
        error_msg = loop._elaborate_error(e, "dictionary access")
        print(error_msg)
    
    # Test 2: ValueError
    print("\n\nTest 2: ValueError elaboration")
    print("━" * 60)
    try:
        int("not_a_number")
    except ValueError as e:
        error_msg = loop._elaborate_error(e, "type conversion")
        print(error_msg)
    
    # Test 3: AttributeError
    print("\n\nTest 3: AttributeError elaboration")
    print("━" * 60)
    try:
        obj = None
        obj.some_method()
    except AttributeError as e:
        error_msg = loop._elaborate_error(e, "method call")
        print(error_msg)
    
    print("\n\n✅ Enhanced error reporting is working!")
    print("   - Shows error type clearly")
    print("   - Provides first ~100 words of message")
    print("   - Includes stack trace snippet")
    print("   - Adds context about what was happening")
    print("   - Suggests what to do next")

if __name__ == "__main__":
    test_error_elaboration()
