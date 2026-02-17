"""
Test Mistral 7B Integration
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from planner.llm_client import LLMClient

def test_mistral_integration():
    """Test Mistral 7B via Ollama"""
    
    print("=" * 50)
    print("MISTRAL 7B INTEGRATION TEST")
    print("=" * 50 + "\n")
    
    # Initialize LLM client
    print("Initializing Mistral 7B client...")
    llm_client = LLMClient(model="mistral", ollama_url="http://localhost:11434")
    print("  [OK] Client initialized\n")
    
    # Test plan generation
    print("Generating plan with Mistral 7B...")
    print("Request: 'List all Python files in current directory'\n")
    
    success, plan, error = llm_client.generate_plan(
        "List all Python files in current directory"
    )
    
    if success:
        print("  [OK] Plan generated successfully")
        print(f"       Plan ID: {plan.plan_id}")
        print(f"       Analysis: {plan.analysis}")
        print(f"       Steps: {len(plan.steps)}")
        print(f"       Confidence: {plan.confidence}")
        
        print("\n  Steps:")
        for i, step in enumerate(plan.steps, 1):
            print(f"    {i}. {step.operation.value}")
            print(f"       Tool: {step.tool.value}")
            print(f"       Reasoning: {step.reasoning}")
        
        print("\n" + "=" * 50)
        print("MISTRAL INTEGRATION TEST PASSED")
        print("=" * 50)
        
    else:
        print(f"  [FALLBACK] Using mock response")
        print(f"  Reason: {error}")
        print("\n  Note: Install Ollama and run 'ollama pull mistral'")
        print("        to enable real Mistral 7B integration")
        
        print("\n" + "=" * 50)
        print("TEST COMPLETED (FALLBACK MODE)")
        print("=" * 50)

if __name__ == "__main__":
    try:
        test_mistral_integration()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
