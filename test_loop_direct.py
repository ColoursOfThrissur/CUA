#!/usr/bin/env python
"""Direct test of improvement loop"""
import asyncio
import sys

async def test_loop():
    print("Importing components...")
    from core.improvement_loop import SelfImprovementLoop
    from planner.llm_client import LLMClient
    from updater.orchestrator import UpdateOrchestrator
    
    print("Creating instances...")
    llm = LLMClient()
    orch = UpdateOrchestrator(".")
    loop = SelfImprovementLoop(llm, orch, max_iterations=1)
    
    print(f"Initial status: {loop.get_status()}")
    
    print("\nStarting loop...")
    result = await loop.start_loop()
    print(f"Start result: {result}")
    
    # Wait a bit for loop to run
    for i in range(10):
        await asyncio.sleep(1)
        status = loop.get_status()
        print(f"[{i+1}s] Status: running={status['running']}, iteration={status['iteration']}, logs={len(status['logs'])}")
        if status['logs']:
            print(f"  Latest log: {status['logs'][-1]}")
        
        if not status['running']:
            print("Loop stopped")
            break
    
    print("\nFinal status:")
    final = loop.get_status()
    print(f"  Running: {final['running']}")
    print(f"  Iteration: {final['iteration']}")
    print(f"  Total logs: {len(final['logs'])}")
    print("\nAll logs:")
    for log in final['logs']:
        print(f"  [{log['timestamp']}] {log['type']}: {log['message']}")

if __name__ == "__main__":
    asyncio.run(test_loop())
