"""
Test Conversational Mode
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from planner.llm_client import LLMClient

def test_conversational_mode():
    """Test conversational responses"""
    
    print("=" * 50)
    print("CONVERSATIONAL MODE TEST")
    print("=" * 50 + "\n")
    
    # Initialize LLM client
    llm_client = LLMClient()
    
    # Test 1: Greeting
    print("Test 1: Greeting")
    print("User: Hello, how are you?")
    response = llm_client.generate_response("Hello, how are you?")
    print(f"CUA: {response}\n")
    
    # Test 2: Capability question
    print("Test 2: Capability Question")
    print("User: What can you do?")
    response = llm_client.generate_response("What can you do?")
    print(f"CUA: {response}\n")
    
    # Test 3: With conversation history
    print("Test 3: With Context")
    history = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi! I'm CUA."},
        {"role": "user", "content": "What's your name?"}
    ]
    response = llm_client.generate_response("What's your name?", history)
    print(f"CUA: {response}\n")
    
    # Test 4: Help request
    print("Test 4: Help Request")
    print("User: How do I list files?")
    response = llm_client.generate_response("How do I list files?")
    print(f"CUA: {response}\n")
    
    print("=" * 50)
    print("CONVERSATIONAL MODE TEST COMPLETED")
    print("=" * 50)

if __name__ == "__main__":
    try:
        test_conversational_mode()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
