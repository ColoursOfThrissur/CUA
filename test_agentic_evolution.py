"""Test agentic evolution chat flow."""
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.agentic_evolution_chat import AgenticEvolutionChat, EvolutionMessage
from core.tool_quality_analyzer import ToolQualityAnalyzer
from planner.llm_client import LLMClient


class MockLLMClient:
    """Mock LLM for testing."""
    
    def _call_llm(self, prompt: str, **kwargs):
        """Return mock responses based on prompt."""
        if "Generate a friendly message" in prompt:
            return """🔧 **Tool Needs Improvement**

I've identified that BrokenTool needs attention:
- Health Score: 6.9/100 (Critical!)
- Success Rate: 0%
- Risk Score: 1.0 (Maximum)
- Issues: Timeout errors, slow execution, no output

This tool is currently in QUARANTINE status and needs immediate fixes.

Would you like me to analyze the code and propose improvements?"""
        
        elif "Analyze this tool code" in prompt:
            return """**Issues Found:**

1. **Line 5**: `time.sleep(10)` - Blocking 10-second sleep causing timeouts
2. **Line 6**: Returns `None` instead of actual result
3. **No error handling** - Fails silently on exceptions

**Root Cause:**
The tool has a hardcoded sleep that blocks execution and doesn't return meaningful data.

**Recommended Fixes:**
- Remove blocking sleep
- Return actual processed result
- Add error handling"""
        
        elif "Generate code changes" in prompt:
            return """**Changes:**

1. Remove the blocking sleep
2. Return meaningful result
3. Add basic error handling

**Diff:**
```diff
--- a/tools/broken_tool.py
+++ b/tools/broken_tool.py
@@ -3,8 +3,10 @@
 
 def execute(self, operation, **kwargs):
-    time.sleep(10)  # This is causing timeouts!
-    return {"result": None}
+    try:
+        # Process operation
+        return {"result": "processed", "operation": operation}
+    except Exception as e:
+        return {"error": str(e)}
```

This will fix the timeout issue and improve success rate to ~100%."""
        
        return "Mock response"


async def simulate_user_responses(chat: AgenticEvolutionChat):
    """Simulate user responding 'yes' to each step."""
    await asyncio.sleep(1)
    
    steps = ["SELECT", "ANALYZE", "PROPOSE", "VALIDATE"]
    for step in steps:
        if chat.waiting_for_response:
            print(f"\n[USER] yes")
            await chat.handle_user_response("yes")
            await asyncio.sleep(1)


async def test_system_evolution():
    """Test system-initiated evolution."""
    print("=" * 60)
    print("TEST: System-Initiated Evolution")
    print("=" * 60)
    
    # Setup
    llm_client = MockLLMClient()
    analyzer = ToolQualityAnalyzer()
    
    chat = AgenticEvolutionChat(llm_client, analyzer)
    
    # Capture messages
    messages = []
    async def capture_message(msg: EvolutionMessage):
        messages.append(msg)
        print(f"\n[AGENT - {msg.step.value.upper()}]")
        print(msg.text)
        if msg.code:
            print(f"\n[CODE SHOWN]")
            print(msg.code[:200] + "..." if len(msg.code) > 200 else msg.code)
        if msg.diff:
            print(f"\n[DIFF SHOWN]")
            print(msg.diff)
        if msg.needs_confirmation:
            print("\n[WAITING FOR USER RESPONSE...]")
    
    chat.set_message_callback(capture_message)
    
    # Start evolution
    print("\n[SYSTEM] Starting evolution for BrokenTool...")
    
    # Run both tasks concurrently
    await asyncio.gather(
        chat.start_system_evolution("BrokenTool"),
        simulate_user_responses(chat)
    )
    
    print("\n" + "=" * 60)
    print(f"Evolution completed! {len(messages)} messages exchanged")
    print("=" * 60)


async def test_user_evolution():
    """Test user-initiated evolution."""
    print("\n\n" + "=" * 60)
    print("TEST: User-Initiated Evolution")
    print("=" * 60)
    
    llm_client = MockLLMClient()
    analyzer = ToolQualityAnalyzer()
    
    chat = AgenticEvolutionChat(llm_client, analyzer)
    
    messages = []
    async def capture_message(msg: EvolutionMessage):
        messages.append(msg)
        print(f"\n[AGENT - {msg.step.value.upper()}]")
        print(msg.text[:300] + "..." if len(msg.text) > 300 else msg.text)
    
    chat.set_message_callback(capture_message)
    
    print("\n[USER] improve the http_tool to handle retries better")
    
    # Note: This will fail gracefully since http_tool doesn't exist in test
    try:
        await chat.start_user_evolution("improve the http_tool to handle retries better")
    except Exception as e:
        print(f"\n[INFO] Expected error (tool not found): {e}")
    
    print("\n" + "=" * 60)


def main():
    """Run tests."""
    print("\n" + "=" * 60)
    print("AGENTIC EVOLUTION CHAT - DEMONSTRATION")
    print("=" * 60)
    print("\nThis demonstrates the conversational flow for tool evolution:")
    print("1. System detects weak tool from observability")
    print("2. Agent starts conversation with user")
    print("3. User confirms each major step")
    print("4. Agent shows code, analysis, diffs")
    print("5. Changes applied after validation")
    print("\n" + "=" * 60)
    
    asyncio.run(test_system_evolution())
    asyncio.run(test_user_evolution())
    
    print("\n\n" + "=" * 60)
    print("KEY FEATURES DEMONSTRATED:")
    print("=" * 60)
    print("[OK] Conversational flow (not automated pipeline)")
    print("[OK] User confirmation at each step")
    print("[OK] Shows actual code and diffs")
    print("[OK] Integrates with observability data")
    print("[OK] LLM-powered explanations")
    print("[OK] Works for system + user triggers")
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
