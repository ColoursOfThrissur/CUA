"""
Pytest configuration and fixtures
"""
import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

@pytest.fixture
def temp_workspace(tmp_path):
    """Create temporary workspace for tests"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    output = tmp_path / "output"
    output.mkdir()
    return {"workspace": str(workspace), "output": str(output)}

@pytest.fixture
def sample_plan():
    """Sample execution plan for testing"""
    from core.plan_schema import ExecutionPlanSchema, PlanStepSchema
    return ExecutionPlanSchema(
        plan_id="test_plan_001",
        analysis="Test plan for unit testing",
        steps=[
            PlanStepSchema(
                step_id="step_1",
                tool="filesystem_tool",
                operation="list_directory",
                parameters={"path": "."},
                reasoning="List files for testing purposes"
            )
        ],
        confidence=1.0
    )

@pytest.fixture
def mock_tool_result():
    """Mock ToolResult for testing"""
    from tools.tool_result import ToolResult, ResultStatus
    return ToolResult(
        tool_name="test_tool",
        capability_name="test_capability",
        status=ResultStatus.SUCCESS,
        data="test_data"
    )
