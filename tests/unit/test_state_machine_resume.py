"""
Unit tests for StateMachine resume and checkpointing
"""
import pytest
import os
from core.state_machine import (
    StateManager, StateMachineExecutor, ExecutionState,
    ExecutionStep, StepState
)
from tools.capability_registry import CapabilityRegistry
from tools.enhanced_filesystem_tool import FilesystemTool

@pytest.mark.unit
class TestStateManager:
    
    def test_save_checkpoint(self, tmp_path, sample_plan):
        """Test saving checkpoint to disk"""
        manager = StateManager(checkpoint_dir=str(tmp_path))
        
        state = ExecutionState(
            execution_id="test_exec_001",
            plan_id="test_plan_001",
            steps=[
                ExecutionStep(
                    step_id="step_1",
                    tool="filesystem_tool",
                    operation="list_directory",
                    parameters={"path": "."},
                    state=StepState.SUCCESS
                )
            ]
        )
        
        checkpoint_file = manager.save_checkpoint(state)
        
        assert os.path.exists(checkpoint_file)
        assert "test_exec_001.json" in checkpoint_file
    
    def test_load_checkpoint(self, tmp_path):
        """Test loading checkpoint from disk"""
        manager = StateManager(checkpoint_dir=str(tmp_path))
        
        # Create and save state
        state = ExecutionState(
            execution_id="test_exec_002",
            plan_id="test_plan_002",
            steps=[
                ExecutionStep(
                    step_id="step_1",
                    tool="filesystem_tool",
                    operation="list_directory",
                    parameters={"path": "."}
                )
            ]
        )
        manager.save_checkpoint(state)
        
        # Load state
        loaded_state = manager.load_checkpoint("test_exec_002")
        
        assert loaded_state is not None
        assert loaded_state.execution_id == "test_exec_002"
        assert len(loaded_state.steps) == 1
    
    def test_load_nonexistent_checkpoint(self, tmp_path):
        """Test loading non-existent checkpoint returns None"""
        manager = StateManager(checkpoint_dir=str(tmp_path))
        
        loaded_state = manager.load_checkpoint("nonexistent")
        
        assert loaded_state is None
    
    def test_delete_checkpoint(self, tmp_path):
        """Test deleting checkpoint"""
        manager = StateManager(checkpoint_dir=str(tmp_path))
        
        state = ExecutionState(
            execution_id="test_exec_003",
            plan_id="test_plan_003",
            steps=[]
        )
        checkpoint_file = manager.save_checkpoint(state)
        
        assert os.path.exists(checkpoint_file)
        
        manager.delete_checkpoint("test_exec_003")
        
        assert not os.path.exists(checkpoint_file)

@pytest.mark.unit
class TestStateMachineExecutor:
    
    @pytest.fixture
    def executor(self, tmp_path):
        """Create executor with registry"""
        registry = CapabilityRegistry()
        tool = FilesystemTool(allowed_roots=[str(tmp_path)])
        registry.register_tool(tool)
        
        manager = StateManager(checkpoint_dir=str(tmp_path / "checkpoints"))
        return StateMachineExecutor(registry, manager)
    
    def test_execute_plan_creates_checkpoint(self, executor, sample_plan, tmp_path):
        """Test executing plan creates checkpoint"""
        exec_id = "test_exec_004"
        
        state = executor.execute_plan(sample_plan, exec_id)
        
        # Checkpoint should exist
        checkpoint_file = tmp_path / "checkpoints" / f"{exec_id}.json"
        assert checkpoint_file.exists()
    
    def test_execute_plan_step_ids_are_1_based(self, executor, sample_plan):
        """Test step IDs are 1-based (step_1, step_2, ...)"""
        exec_id = "test_exec_005"
        
        state = executor.execute_plan(sample_plan, exec_id)
        
        assert state.steps[0].step_id == "step_1"
    
    def test_execute_plan_tracks_progress(self, executor, sample_plan):
        """Test execution tracks progress correctly"""
        exec_id = "test_exec_006"
        
        state = executor.execute_plan(sample_plan, exec_id)
        progress = executor.get_progress(state)
        
        assert progress["execution_id"] == exec_id
        assert progress["total_steps"] == len(sample_plan.steps)
        assert "completed_steps" in progress
        assert "progress_percent" in progress
    
    def test_resume_execution_from_checkpoint(self, executor, sample_plan, tmp_path):
        """Test resuming execution from checkpoint"""
        exec_id = "test_exec_007"
        
        # Create a partially completed state
        state = ExecutionState(
            execution_id=exec_id,
            plan_id=sample_plan.plan_id,
            steps=[
                ExecutionStep(
                    step_id="step_1",
                    tool="filesystem_tool",
                    operation="list_directory",
                    parameters={"path": str(tmp_path)},
                    state=StepState.SUCCESS
                ),
                ExecutionStep(
                    step_id="step_2",
                    tool="filesystem_tool",
                    operation="list_directory",
                    parameters={"path": str(tmp_path)},
                    state=StepState.PENDING
                )
            ],
            current_step_index=1,
            overall_state="running"
        )
        
        executor.state_manager.save_checkpoint(state)
        
        # Resume execution
        resumed_state = executor.resume_execution(exec_id)
        
        assert resumed_state.execution_id == exec_id
        assert resumed_state.steps[0].state == StepState.SUCCESS
    
    def test_execution_stops_on_failure(self, executor, tmp_path):
        """Test execution stops when step fails"""
        from planner.plan_parser import ExecutionPlan, PlanStep
        
        # Create plan with invalid operation
        plan = ExecutionPlan(
            plan_id="fail_plan",
            analysis="Plan that will fail because file doesn't exist",
            steps=[
                PlanStep(
                    step_id="step_1",
                    tool="filesystem_tool",
                    operation="read_file",
                    parameters={"path": str(tmp_path / "nonexistent.txt")},
                    reasoning="This will fail because file doesn't exist"
                )
            ],
            confidence=1.0
        )
        
        state = executor.execute_plan(plan, "fail_exec")
        
        assert state.overall_state == "failed"
        assert state.steps[0].state == StepState.FAILED
    
    def test_get_progress_calculates_percentage(self, executor, sample_plan):
        """Test progress percentage is calculated correctly"""
        exec_id = "test_exec_008"
        
        state = executor.execute_plan(sample_plan, exec_id)
        progress = executor.get_progress(state)
        
        expected_percent = (progress["completed_steps"] / progress["total_steps"]) * 100
        assert progress["progress_percent"] == expected_percent

@pytest.mark.unit
class TestExecutionStateTracking:
    
    def test_execution_step_state_transitions(self):
        """Test step state transitions"""
        step = ExecutionStep(
            step_id="step_1",
            tool="test_tool",
            operation="test_op",
            parameters={}
        )
        
        assert step.state == StepState.PENDING
        
        step.state = StepState.RUNNING
        assert step.state == StepState.RUNNING
        
        step.state = StepState.SUCCESS
        assert step.state == StepState.SUCCESS
    
    def test_execution_state_timestamps(self):
        """Test execution state tracks timestamps"""
        import time
        
        state = ExecutionState(
            execution_id="test_exec",
            plan_id="test_plan",
            steps=[]
        )
        
        assert state.created_at is not None
        assert state.created_at <= time.time()
        
        state.completed_at = time.time()
        assert state.completed_at >= state.created_at
