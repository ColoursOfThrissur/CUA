"""
Full Pipeline Integration Test
Tests LLM -> Validation -> Execution flow
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from planner.llm_client import LLMClient
from core.plan_validator import PlanValidator
from core.state_machine import StateManager, StateMachineExecutor
from tools.capability_registry import CapabilityRegistry
from tools.enhanced_filesystem_tool import FilesystemTool
from uuid import uuid4

def test_full_pipeline():
    """Test complete pipeline: LLM -> Validation -> Execution"""
    
    print("=" * 50)
    print("FULL PIPELINE INTEGRATION TEST")
    print("=" * 50 + "\n")
    
    # Initialize components
    print("Initializing components...")
    llm_client = LLMClient()
    plan_validator = PlanValidator()
    registry = CapabilityRegistry()
    fs_tool = FilesystemTool()
    registry.register_tool(fs_tool)
    state_manager = StateManager()
    sm_executor = StateMachineExecutor(registry, state_manager)
    print("  [OK] Components initialized\n")
    
    # Step 1: Generate plan
    print("Step 1: Generate plan from user request...")
    user_request = "List files in current directory"
    success, plan, error = llm_client.generate_plan(user_request)
    
    assert success, f"Plan generation failed: {error}"
    assert plan is not None
    print(f"  [OK] Plan generated: {plan.plan_id}")
    print(f"       Steps: {len(plan.steps)}")
    print(f"       Confidence: {plan.confidence}\n")
    
    # Step 2: Validate plan
    print("Step 2: Validate plan...")
    validation = plan_validator.validate_plan(plan)
    
    assert validation.is_approved, f"Plan rejected: {validation.reasons}"
    print(f"  [OK] Plan approved")
    print(f"       Risk: {validation.risk_assessment.value}")
    print(f"       Steps validated: {validation.total_steps}\n")
    
    # Step 3: Execute plan
    print("Step 3: Execute plan with state machine...")
    exec_id = str(uuid4())
    exec_state = sm_executor.execute_plan(plan, exec_id)
    
    assert exec_state.overall_state == "completed", f"Execution failed: {exec_state.overall_state}"
    print(f"  [OK] Execution completed")
    print(f"       Execution ID: {exec_id}")
    
    # Step 4: Check progress
    print("\nStep 4: Check execution progress...")
    progress = sm_executor.get_progress(exec_state)
    
    print(f"  [OK] Progress retrieved")
    print(f"       Total steps: {progress['total_steps']}")
    print(f"       Completed: {progress['completed_steps']}")
    print(f"       Progress: {progress['progress_percent']:.1f}%\n")
    
    # Step 5: Verify checkpoint
    print("Step 5: Verify checkpoint saved...")
    loaded_state = state_manager.load_checkpoint(exec_id)
    
    assert loaded_state is not None, "Checkpoint not found"
    assert loaded_state.execution_id == exec_id
    print(f"  [OK] Checkpoint verified")
    print(f"       State: {loaded_state.overall_state}\n")
    
    print("=" * 50)
    print("FULL PIPELINE TEST PASSED")
    print("=" * 50)

if __name__ == "__main__":
    try:
        test_full_pipeline()
    except AssertionError as e:
        print(f"\nTEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
