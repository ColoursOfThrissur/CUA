"""
Integration tests for full pipeline
"""
import pytest
from uuid import uuid4

@pytest.mark.integration
class TestFullPipeline:
    
    @pytest.fixture
    def pipeline_components(self, tmp_path):
        """Setup full pipeline components"""
        from planner.llm_client import LLMClient
        from core.plan_validator import PlanValidator
        from core.state_machine import StateManager, StateMachineExecutor
        from tools.capability_registry import CapabilityRegistry
        from tools.enhanced_filesystem_tool import FilesystemTool
        
        llm_client = LLMClient()
        plan_validator = PlanValidator()
        registry = CapabilityRegistry()
        fs_tool = FilesystemTool(allowed_roots=[str(tmp_path)])
        registry.register_tool(fs_tool)
        state_manager = StateManager(checkpoint_dir=str(tmp_path / "checkpoints"))
        
        return {
            "llm_client": llm_client,
            "plan_validator": plan_validator,
            "registry": registry,
            "state_manager": state_manager
        }
    
    def test_plan_generation_to_execution(self, pipeline_components, tmp_path):
        """Test complete flow: LLM → Validation → Execution"""
        from core.state_machine import StateMachineExecutor
        
        llm = pipeline_components["llm_client"]
        validator = pipeline_components["plan_validator"]
        registry = pipeline_components["registry"]
        state_manager = pipeline_components["state_manager"]
        
        # Step 1: Generate plan
        success, plan, error = llm.generate_plan("List files in current directory")
        assert success, f"Plan generation failed: {error}"
        
        # Step 2: Validate plan
        validation = validator.validate_plan(plan)
        assert validation.is_approved, f"Plan rejected: {validation.reasons}"
        
        # Step 3: Execute plan
        exec_id = str(uuid4())
        executor = StateMachineExecutor(registry, state_manager)
        exec_state = executor.execute_plan(plan, exec_id)
        
        # Step 4: Verify execution
        assert exec_state.overall_state in ["completed", "failed"]
        
        # Step 5: Check checkpoint
        loaded_state = state_manager.load_checkpoint(exec_id)
        assert loaded_state is not None
        assert loaded_state.execution_id == exec_id
    
    def test_plan_validation_rejects_invalid(self, pipeline_components):
        """Test plan validation rejects invalid plans"""
        from core.plan_schema import ExecutionPlanSchema, PlanStepSchema, ToolName, OperationName
        from pydantic import ValidationError
        
        validator = pipeline_components["plan_validator"]
        
        # Try to create plan with too many steps (>20) - should fail Pydantic validation
        with pytest.raises(ValidationError) as exc_info:
            steps = [
                PlanStepSchema(
                    step_id=f"step_{i+1}",
                    tool=ToolName.FILESYSTEM_TOOL,
                    operation=OperationName.LIST_DIRECTORY,
                    parameters={"path": "."},
                    reasoning="Test step for validation rejection test"
                )
                for i in range(25)  # >20 max
            ]
            
            plan = ExecutionPlanSchema(
                plan_id="invalid_plan",
                analysis="Plan with too many steps for testing validation",
                steps=steps,
                confidence=0.5
            )
        
        # Verify it failed due to step count
        assert "steps" in str(exc_info.value)
    
    def test_execution_with_checkpoint_resume(self, pipeline_components, tmp_path):
        """Test execution can be resumed from checkpoint"""
        from core.plan_schema import ExecutionPlanSchema, PlanStepSchema, ToolName, OperationName
        from core.state_machine import StateMachineExecutor
        
        registry = pipeline_components["registry"]
        state_manager = pipeline_components["state_manager"]
        
        # Create multi-step plan
        plan = ExecutionPlanSchema(
            plan_id="resume_test_plan",
            analysis="Multi-step plan for resume testing",
            steps=[
                PlanStepSchema(
                    step_id="step_1",
                    tool=ToolName.FILESYSTEM_TOOL,
                    operation=OperationName.LIST_DIRECTORY,
                    parameters={"path": str(tmp_path)},
                    reasoning="List files in test directory"
                ),
                PlanStepSchema(
                    step_id="step_2",
                    tool=ToolName.FILESYSTEM_TOOL,
                    operation=OperationName.LIST_DIRECTORY,
                    parameters={"path": str(tmp_path)},
                    reasoning="List files again for testing"
                )
            ],
            confidence=1.0
        )
        
        exec_id = str(uuid4())
        executor = StateMachineExecutor(registry, state_manager)
        
        # Execute plan
        state1 = executor.execute_plan(plan, exec_id)
        
        # Resume execution (should complete immediately if already done)
        state2 = executor.resume_execution(exec_id)
        
        assert state2.execution_id == exec_id
        assert state2.overall_state == state1.overall_state

@pytest.mark.integration
class TestAPIIntegration:
    
    def test_api_server_imports(self):
        """Test API server imports all required components"""
        try:
            from api import server
            assert hasattr(server, 'app')
            assert hasattr(server, 'registry')
            assert hasattr(server, 'llm_client')
            assert hasattr(server, 'permission_gate')
        except ImportError as e:
            pytest.fail(f"API server import failed: {e}")
    
    def test_conversational_mode_integration(self):
        """Test conversational mode works end-to-end"""
        from planner.llm_client import LLMClient
        
        llm = LLMClient()
        
        # Test conversational response
        response = llm.generate_response("Hello, how are you?")
        assert response is not None
        assert len(response) > 0
        
        # Test with history
        history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"}
        ]
        response = llm.generate_response("What's your name?", history)
        assert response is not None

@pytest.mark.integration
@pytest.mark.slow
class TestSecurityIntegration:
    
    def test_permission_gate_blocks_excessive_writes(self, tmp_path):
        """Test permission gate blocks excessive writes"""
        from core.session_permissions import PermissionGate
        
        gate = PermissionGate()
        session_id = "test_session"
        
        # Write up to limit (10 writes) - use relative paths in output dir
        for i in range(10):
            result = gate.check_permission(
                session_id,
                "filesystem_tool",
                "write_file",
                {"path": f"./output/test_file_{i}.txt", "content": "test"}
            )
            if not result.is_valid:
                pytest.fail(f"Write {i+1} blocked unexpectedly: {result.reason}")
            gate.record_operation(session_id, "filesystem_tool", "write_file", True)
        
        # 11th write should be blocked
        result = gate.check_permission(
            session_id,
            "filesystem_tool",
            "write_file",
            {"path": "./output/test_file_11.txt", "content": "test"}
        )
        assert not result.is_valid, f"Expected write to be blocked but got: {result.reason}"
    
    def test_brain_stem_blocks_dangerous_paths(self):
        """Test BrainStem blocks dangerous paths"""
        from core.immutable_brain_stem import BrainStem
        
        dangerous_paths = [
            "C:\\Windows\\system32\\test.txt",
            "/etc/passwd",
            "~/.ssh/id_rsa",
            "./output/../../etc/passwd"
        ]
        
        for path in dangerous_paths:
            result = BrainStem.validate_path(path)
            assert not result.is_valid, f"Dangerous path not blocked: {path}"
