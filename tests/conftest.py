"""
Pytest configuration and fixtures
"""
import pytest
import sys
import os
import shutil
import uuid
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def tmp_path(request) -> Path:
    """
    Local replacement for pytest's built-in tmp_path fixture.

    The default tmpdir/tmp_path plugins can fail in restricted Windows environments.
    This fixture creates a per-test temp directory under the repo (test_tmp/).
    """
    base = Path("test_tmp")
    base.mkdir(exist_ok=True)

    name = "".join(ch for ch in request.node.name if ch.isalnum() or ch in ("-", "_"))
    path = base / f"{name}_{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


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
    from application.dto.plan_schema import ExecutionPlanSchema, PlanStepSchema
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
