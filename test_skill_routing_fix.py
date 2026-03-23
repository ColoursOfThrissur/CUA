#!/usr/bin/env python3
"""
Test script to verify skill routing fix for conversational requests
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.skills.registry import SkillRegistry
from core.skills.selector import SkillSelector

def test_conversation_routing():
    """Test that conversational requests are properly routed to conversation skill"""
    
    # Initialize registry and selector
    registry = SkillRegistry()
    registry.load_all()
    selector = SkillSelector()
    
    # Test cases that were failing before
    test_cases = [
        "hi",
        "Hi", 
        "hello",
        "hey",
        "hi how are you",
        "good morning",
        "thanks",
        "bye"
    ]
    
    print("Testing conversation skill routing...")
    print("=" * 50)
    
    for test_message in test_cases:
        result = selector.select_skill(test_message, registry)
        
        print(f"Message: '{test_message}'")
        print(f"  Matched: {result.matched}")
        print(f"  Skill: {result.skill_name}")
        print(f"  Category: {result.category}")
        print(f"  Confidence: {result.confidence}")
        print(f"  Reason: {result.reason}")
        print(f"  Fallback: {result.fallback_mode}")
        
        # Check if routing is correct
        if result.matched and result.skill_name == "conversation":
            print("  PASS - Correctly routed to conversation skill")
        else:
            print("  FAIL - Should route to conversation skill")
        
        print()
    
    print("Test completed!")

if __name__ == "__main__":
    test_conversation_routing()