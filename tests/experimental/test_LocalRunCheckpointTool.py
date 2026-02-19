"""
Tests for experimental LocalRunCheckpointTool
"""
from tools.experimental.LocalRunCheckpointTool import LocalRunCheckpointTool
from tools.tool_result import ResultStatus


def test_local_run_checkpoint_tool_basic():
    tool = LocalRunCheckpointTool()
    assert tool is not None


def test_local_run_checkpoint_tool_create_read_list():
    tool = LocalRunCheckpointTool()
    create_result = tool.execute(
        "create",
        checkpoint_id="demo-001",
        notes="baseline",
        tags=["cua"],
        metadata={"source": "test"},
    )
    assert create_result.status == ResultStatus.SUCCESS

    read_result = tool.execute("read", checkpoint_id="demo-001")
    assert read_result.status == ResultStatus.SUCCESS
    assert read_result.data["checkpoint_id"] == "demo-001"

    list_result = tool.execute("list", limit=5)
    assert list_result.status == ResultStatus.SUCCESS
    assert isinstance(list_result.data, list)
