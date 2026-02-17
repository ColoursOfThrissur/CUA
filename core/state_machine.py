"""
Execution State Machine - Foundation for reliable multi-step execution
"""

from enum import Enum
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
import json
import time
from pathlib import Path

class StepState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"

@dataclass
class ExecutionStep:
    step_id: str
    tool: str
    operation: str
    parameters: Dict[str, Any]
    state: StepState = StepState.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    retry_count: int = 0

@dataclass
class ExecutionState:
    execution_id: str
    plan_id: str
    steps: List[ExecutionStep]
    current_step_index: int = 0
    overall_state: str = "pending"
    created_at: float = None
    completed_at: Optional[float] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()

class StateManager:
    """Manages execution state with checkpointing"""
    
    def __init__(self, checkpoint_dir: str = "./checkpoints"):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(exist_ok=True)
    
    def save_checkpoint(self, state: ExecutionState) -> str:
        """Save execution state to disk"""
        checkpoint_file = self.checkpoint_dir / f"{state.execution_id}.json"
        
        # Convert to dict
        state_dict = {
            "execution_id": state.execution_id,
            "plan_id": state.plan_id,
            "current_step_index": state.current_step_index,
            "overall_state": state.overall_state,
            "created_at": state.created_at,
            "completed_at": state.completed_at,
            "steps": [
                {
                    "step_id": step.step_id,
                    "tool": step.tool,
                    "operation": step.operation,
                    "parameters": step.parameters,
                    "state": step.state.value,
                    "result": step.result,
                    "error": step.error,
                    "started_at": step.started_at,
                    "completed_at": step.completed_at,
                    "retry_count": step.retry_count
                }
                for step in state.steps
            ]
        }
        
        with open(checkpoint_file, 'w') as f:
            json.dump(state_dict, f, indent=2)
        
        return str(checkpoint_file)
    
    def load_checkpoint(self, execution_id: str) -> Optional[ExecutionState]:
        """Load execution state from disk"""
        checkpoint_file = self.checkpoint_dir / f"{execution_id}.json"
        
        if not checkpoint_file.exists():
            return None
        
        with open(checkpoint_file, 'r') as f:
            state_dict = json.load(f)
        
        # Reconstruct state
        steps = [
            ExecutionStep(
                step_id=step["step_id"],
                tool=step["tool"],
                operation=step["operation"],
                parameters=step["parameters"],
                state=StepState(step["state"]),
                result=step.get("result"),
                error=step.get("error"),
                started_at=step.get("started_at"),
                completed_at=step.get("completed_at"),
                retry_count=step.get("retry_count", 0)
            )
            for step in state_dict["steps"]
        ]
        
        return ExecutionState(
            execution_id=state_dict["execution_id"],
            plan_id=state_dict["plan_id"],
            steps=steps,
            current_step_index=state_dict["current_step_index"],
            overall_state=state_dict["overall_state"],
            created_at=state_dict["created_at"],
            completed_at=state_dict.get("completed_at")
        )
    
    def delete_checkpoint(self, execution_id: str):
        """Delete checkpoint after successful completion"""
        checkpoint_file = self.checkpoint_dir / f"{execution_id}.json"
        if checkpoint_file.exists():
            checkpoint_file.unlink()

class StateMachineExecutor:
    """Executes plans with state machine and checkpointing"""
    
    def __init__(self, tool_registry, state_manager: StateManager):
        self.registry = tool_registry
        self.state_manager = state_manager
    
    def execute_plan(self, plan, execution_id: str) -> ExecutionState:
        """Execute plan with state tracking"""
        
        # Create initial state with 1-based step IDs
        steps = [
            ExecutionStep(
                step_id=f"step_{i+1}",  # 1-based to match schema
                tool=step.tool,
                operation=step.operation,
                parameters=step.parameters
            )
            for i, step in enumerate(plan.steps)
        ]
        
        state = ExecutionState(
            execution_id=execution_id,
            plan_id=plan.plan_id,
            steps=steps,
            overall_state="running"
        )
        
        # Save initial checkpoint
        self.state_manager.save_checkpoint(state)
        
        # Execute steps
        while state.current_step_index < len(state.steps):
            step = state.steps[state.current_step_index]
            
            # Execute step
            self._execute_step(state, step)
            
            # Save checkpoint after each step
            self.state_manager.save_checkpoint(state)
            
            # Stop on failure
            if step.state == StepState.FAILED:
                state.overall_state = "failed"
                break
            
            # Move to next step
            state.current_step_index += 1
        
        # Mark as complete if all steps succeeded
        if state.current_step_index >= len(state.steps):
            state.overall_state = "completed"
            state.completed_at = time.time()
        
        # Final checkpoint
        self.state_manager.save_checkpoint(state)
        
        return state
    
    def resume_execution(self, execution_id: str) -> ExecutionState:
        """Resume execution from checkpoint"""
        
        # Load state
        state = self.state_manager.load_checkpoint(execution_id)
        if not state:
            raise ValueError(f"No checkpoint found for {execution_id}")
        
        # Continue from current step
        while state.current_step_index < len(state.steps):
            step = state.steps[state.current_step_index]
            
            # Skip already completed steps
            if step.state == StepState.SUCCESS:
                state.current_step_index += 1
                continue
            
            # Execute step
            self._execute_step(state, step)
            
            # Save checkpoint
            self.state_manager.save_checkpoint(state)
            
            # Stop on failure
            if step.state == StepState.FAILED:
                state.overall_state = "failed"
                break
            
            state.current_step_index += 1
        
        # Mark as complete
        if state.current_step_index >= len(state.steps):
            state.overall_state = "completed"
            state.completed_at = time.time()
        
        self.state_manager.save_checkpoint(state)
        return state
    
    def _execute_step(self, state: ExecutionState, step: ExecutionStep):
        """Execute single step with state tracking"""
        
        step.state = StepState.RUNNING
        step.started_at = time.time()
        
        try:
            # Get tool
            tool = self.registry.get_tool_by_name(step.tool)
            if not tool:
                raise ValueError(f"Tool '{step.tool}' not found")
            
            # Execute - handle both string and enum operation names
            operation = step.operation
            if hasattr(operation, 'value'):
                operation = operation.value
            
            result = tool.execute(operation, step.parameters)
            
            # Standardized success check using ToolResult.is_success()
            if hasattr(result, 'is_success'):
                success = result.is_success()
            elif hasattr(result, 'status'):
                success = result.status.value == "success"
            else:
                success = False
            
            if success:
                step.state = StepState.SUCCESS
                step.result = getattr(result, 'data', None)
            else:
                step.state = StepState.FAILED
                step.error = getattr(result, 'error_message', 'Unknown error')
            
        except Exception as e:
            step.state = StepState.FAILED
            step.error = str(e)
        
        step.completed_at = time.time()
    
    def get_progress(self, state: ExecutionState) -> Dict:
        """Get execution progress"""
        completed = sum(1 for s in state.steps if s.state == StepState.SUCCESS)
        failed = sum(1 for s in state.steps if s.state == StepState.FAILED)
        
        return {
            "execution_id": state.execution_id,
            "overall_state": state.overall_state,
            "total_steps": len(state.steps),
            "completed_steps": completed,
            "failed_steps": failed,
            "current_step": state.current_step_index,
            "progress_percent": (completed / len(state.steps)) * 100 if state.steps else 0
        }
