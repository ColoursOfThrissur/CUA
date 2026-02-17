"""
Test State Machine - Verify checkpoint and resume functionality
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.state_machine import StateMachineExecutor, StateManager, ExecutionStep, StepState
from tools.capability_registry import CapabilityRegistry
from tools.enhanced_filesystem_tool import FilesystemTool
from planner.plan_parser import ExecutionPlan, PlanStep
from uuid import uuid4

def test_state_machine():
    print("=== TESTING STATE MACHINE ===\n")
    
    # Setup
    registry = CapabilityRegistry()
    fs_tool = FilesystemTool()
    registry.register_tool(fs_tool)
    
    state_manager = StateManager()
    executor = StateMachineExecutor(registry, state_manager)
    
    # Test 1: Execute 3-step plan
    print("1. Testing 3-step execution...")
    plan = ExecutionPlan(
        plan_id="test_plan",
        analysis="Test multi-step",
        steps=[
            PlanStep("step1", "filesystem_tool", "write_file", 
                    {"path": "./output/step1.txt", "content": "Step 1"}, ""),
            PlanStep("step2", "filesystem_tool", "write_file",
                    {"path": "./output/step2.txt", "content": "Step 2"}, ""),
            PlanStep("step3", "filesystem_tool", "list_directory",
                    {"path": "./output"}, "")
        ],
        confidence=0.9,
        raw_response=""
    )
    
    execution_id = str(uuid4())
    state = executor.execute_plan(plan, execution_id)
    
    print(f"   Execution ID: {execution_id}")
    print(f"   Overall state: {state.overall_state}")
    print(f"   Steps completed: {state.current_step_index}/{len(state.steps)}")
    
    # Verify all steps succeeded
    success_count = sum(1 for s in state.steps if s.state == StepState.SUCCESS)
    print(f"   Successful steps: {success_count}")
    
    assert state.overall_state == "completed", "Execution should complete"
    assert success_count == 3, "All 3 steps should succeed"
    print("   PASS: 3-step execution works\n")
    
    # Test 2: Checkpoint saved
    print("2. Testing checkpoint save...")
    loaded_state = state_manager.load_checkpoint(execution_id)
    assert loaded_state is not None, "Checkpoint should exist"
    assert loaded_state.execution_id == execution_id, "IDs should match"
    assert len(loaded_state.steps) == 3, "Should have 3 steps"
    print("   PASS: Checkpoint saved and loaded\n")
    
    # Test 3: Resume from checkpoint
    print("3. Testing resume capability...")
    
    # Create plan that will partially execute
    plan2 = ExecutionPlan(
        plan_id="test_plan2",
        analysis="Test resume",
        steps=[
            PlanStep("step1", "filesystem_tool", "write_file",
                    {"path": "./output/resume1.txt", "content": "Resume 1"}, ""),
            PlanStep("step2", "filesystem_tool", "write_file",
                    {"path": "./output/resume2.txt", "content": "Resume 2"}, "")
        ],
        confidence=0.9,
        raw_response=""
    )
    
    execution_id2 = str(uuid4())
    
    # Execute first step only (simulate interruption)
    state2 = executor.execute_plan(plan2, execution_id2)
    
    # Manually mark as incomplete for testing
    if state2.overall_state == "completed":
        print("   Note: Plan completed fully, simulating partial execution")
        # Load and modify checkpoint
        state2 = state_manager.load_checkpoint(execution_id2)
        state2.current_step_index = 1
        state2.overall_state = "running"
        state2.steps[1].state = StepState.PENDING
        state_manager.save_checkpoint(state2)
    
    # Resume execution
    resumed_state = executor.resume_execution(execution_id2)
    
    print(f"   Resumed execution: {resumed_state.overall_state}")
    print(f"   Steps after resume: {resumed_state.current_step_index}/{len(resumed_state.steps)}")
    
    assert resumed_state.overall_state == "completed", "Should complete after resume"
    print("   PASS: Resume works\n")
    
    # Test 4: Progress tracking
    print("4. Testing progress tracking...")
    progress = executor.get_progress(state)
    
    print(f"   Progress: {progress['progress_percent']:.0f}%")
    print(f"   Completed: {progress['completed_steps']}/{progress['total_steps']}")
    
    assert progress['progress_percent'] == 100, "Should be 100% complete"
    print("   PASS: Progress tracking works\n")
    
    # Cleanup
    state_manager.delete_checkpoint(execution_id)
    state_manager.delete_checkpoint(execution_id2)
    
    if os.path.exists("./output/step1.txt"):
        os.remove("./output/step1.txt")
    if os.path.exists("./output/step2.txt"):
        os.remove("./output/step2.txt")
    if os.path.exists("./output/resume1.txt"):
        os.remove("./output/resume1.txt")
    if os.path.exists("./output/resume2.txt"):
        os.remove("./output/resume2.txt")
    
    print("=== ALL STATE MACHINE TESTS PASSED ===")
    print("\nState Machine Features Verified:")
    print("- Multi-step execution")
    print("- Checkpoint save/load")
    print("- Resume from checkpoint")
    print("- Progress tracking")
    print("- State transitions")
    
    return True

if __name__ == "__main__":
    try:
        test_state_machine()
    except Exception as e:
        print(f"\nTEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
