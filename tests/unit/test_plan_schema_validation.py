"""
Unit tests for plan schema validation
"""
import pytest
from core.plan_schema import (
    ExecutionPlanSchema, PlanStepSchema, validate_plan_json,
    ToolName, OperationName
)

@pytest.mark.unit
class TestPlanStepSchema:
    
    def test_valid_plan_step(self):
        """Test valid plan step is accepted"""
        step = PlanStepSchema(
            step_id="step_1",
            tool=ToolName.FILESYSTEM_TOOL,
            operation=OperationName.LIST_DIRECTORY,
            parameters={"path": "."},
            reasoning="List files in current directory"
        )
        assert step.step_id == "step_1"
    
    def test_invalid_step_id_format(self):
        """Test invalid step_id format is rejected"""
        with pytest.raises(ValueError):
            PlanStepSchema(
                step_id="invalid_id",
                tool=ToolName.FILESYSTEM_TOOL,
                operation=OperationName.LIST_DIRECTORY,
                parameters={"path": "."},
                reasoning="Test step"
            )
    
    def test_read_file_requires_path(self):
        """Test read_file operation requires path parameter"""
        with pytest.raises(ValueError, match="requires 'path'"):
            PlanStepSchema(
                step_id="step_1",
                tool=ToolName.FILESYSTEM_TOOL,
                operation=OperationName.READ_FILE,
                parameters={},
                reasoning="Test read without path"
            )
    
    def test_write_file_requires_path_and_content(self):
        """Test write_file operation requires path and content"""
        with pytest.raises(ValueError, match="requires 'path' and 'content'"):
            PlanStepSchema(
                step_id="step_1",
                tool=ToolName.FILESYSTEM_TOOL,
                operation=OperationName.WRITE_FILE,
                parameters={"path": "./test.txt"},
                reasoning="Test write without content"
            )
    
    def test_write_file_content_size_limit(self):
        """Test write_file content size limit is enforced"""
        large_content = "x" * (1024 * 1024 + 1)  # >1MB
        
        with pytest.raises(ValueError, match="exceeds 1MB limit"):
            PlanStepSchema(
                step_id="step_1",
                tool=ToolName.FILESYSTEM_TOOL,
                operation=OperationName.WRITE_FILE,
                parameters={"path": "./test.txt", "content": large_content},
                reasoning="Test large content"
            )
    
    def test_reasoning_length_validation(self):
        """Test reasoning length is validated"""
        # Too short
        with pytest.raises(ValueError):
            PlanStepSchema(
                step_id="step_1",
                tool=ToolName.FILESYSTEM_TOOL,
                operation=OperationName.LIST_DIRECTORY,
                parameters={"path": "."},
                reasoning="Short"
            )
        
        # Too long
        with pytest.raises(ValueError):
            PlanStepSchema(
                step_id="step_1",
                tool=ToolName.FILESYSTEM_TOOL,
                operation=OperationName.LIST_DIRECTORY,
                parameters={"path": "."},
                reasoning="x" * 501
            )

@pytest.mark.unit
class TestExecutionPlanSchema:
    
    def test_valid_execution_plan(self):
        """Test valid execution plan is accepted"""
        plan = ExecutionPlanSchema(
            plan_id="plan_001",
            analysis="User wants to list files",
            steps=[
                PlanStepSchema(
                    step_id="step_1",
                    tool=ToolName.FILESYSTEM_TOOL,
                    operation=OperationName.LIST_DIRECTORY,
                    parameters={"path": "."},
                    reasoning="List all files in current directory"
                )
            ],
            confidence=0.95
        )
        assert plan.plan_id == "plan_001"
        assert len(plan.steps) == 1
    
    def test_plan_requires_at_least_one_step(self):
        """Test plan must have at least one step"""
        with pytest.raises(ValueError):
            ExecutionPlanSchema(
                plan_id="plan_001",
                analysis="Empty plan",
                steps=[],
                confidence=0.5
            )
    
    def test_plan_max_steps_limit(self):
        """Test plan cannot exceed max steps"""
        steps = [
            PlanStepSchema(
                step_id=f"step_{i+1}",
                tool=ToolName.FILESYSTEM_TOOL,
                operation=OperationName.LIST_DIRECTORY,
                parameters={"path": "."},
                reasoning="Test step for max limit validation"
            )
            for i in range(21)  # >20 steps
        ]
        
        with pytest.raises(ValueError):
            ExecutionPlanSchema(
                plan_id="plan_001",
                analysis="Too many steps",
                steps=steps,
                confidence=0.5
            )
    
    def test_confidence_range_validation(self):
        """Test confidence must be between 0 and 1"""
        # Too low
        with pytest.raises(ValueError):
            ExecutionPlanSchema(
                plan_id="plan_001",
                analysis="Test",
                steps=[
                    PlanStepSchema(
                        step_id="step_1",
                        tool=ToolName.FILESYSTEM_TOOL,
                        operation=OperationName.LIST_DIRECTORY,
                        parameters={"path": "."},
                        reasoning="Test step for confidence validation"
                    )
                ],
                confidence=-0.1
            )
        
        # Too high
        with pytest.raises(ValueError):
            ExecutionPlanSchema(
                plan_id="plan_001",
                analysis="Test",
                steps=[
                    PlanStepSchema(
                        step_id="step_1",
                        tool=ToolName.FILESYSTEM_TOOL,
                        operation=OperationName.LIST_DIRECTORY,
                        parameters={"path": "."},
                        reasoning="Test step for confidence validation"
                    )
                ],
                confidence=1.5
            )
    
    def test_step_dependency_validation(self):
        """Test step dependencies are validated"""
        with pytest.raises(ValueError, match="depends on non-existent"):
            ExecutionPlanSchema(
                plan_id="plan_001",
                analysis="Test dependencies",
                steps=[
                    PlanStepSchema(
                        step_id="step_1",
                        tool=ToolName.FILESYSTEM_TOOL,
                        operation=OperationName.LIST_DIRECTORY,
                        parameters={"path": "."},
                        reasoning="First step with invalid dependency",
                        depends_on=["step_999"]  # Non-existent
                    )
                ],
                confidence=0.5
            )
    
    def test_valid_step_dependencies(self):
        """Test valid step dependencies are accepted"""
        plan = ExecutionPlanSchema(
            plan_id="plan_001",
            analysis="Test valid dependencies",
            steps=[
                PlanStepSchema(
                    step_id="step_1",
                    tool=ToolName.FILESYSTEM_TOOL,
                    operation=OperationName.LIST_DIRECTORY,
                    parameters={"path": "."},
                    reasoning="First step lists files in directory"
                ),
                PlanStepSchema(
                    step_id="step_2",
                    tool=ToolName.FILESYSTEM_TOOL,
                    operation=OperationName.WRITE_FILE,
                    parameters={"path": "./summary.txt", "content": "Summary"},
                    reasoning="Second step creates summary file",
                    depends_on=["step_1"]
                )
            ],
            confidence=0.9
        )
        assert len(plan.steps) == 2
        assert plan.steps[1].depends_on == ["step_1"]

@pytest.mark.unit
class TestValidatePlanJson:
    
    def test_validate_valid_plan_json(self):
        """Test validating valid plan JSON"""
        plan_json = {
            "plan_id": "plan_001",
            "analysis": "User wants to list files",
            "steps": [
                {
                    "step_id": "step_1",
                    "tool": "filesystem_tool",
                    "operation": "list_directory",
                    "parameters": {"path": "."},
                    "reasoning": "List all files in current directory"
                }
            ],
            "confidence": 0.95
        }
        
        is_valid, plan, error = validate_plan_json(plan_json)
        
        assert is_valid
        assert plan is not None
        assert error is None
    
    def test_validate_invalid_plan_json(self):
        """Test validating invalid plan JSON"""
        plan_json = {
            "plan_id": "plan_001",
            "steps": []  # Missing analysis, empty steps
        }
        
        is_valid, plan, error = validate_plan_json(plan_json)
        
        assert not is_valid
        assert plan is None
        assert error is not None
