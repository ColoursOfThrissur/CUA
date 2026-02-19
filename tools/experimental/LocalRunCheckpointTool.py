"""
LocalRunCheckpointTool - Auto-generated tool
"""
from pathlib import Path
import json
from datetime import datetime, timezone
from tools.tool_interface import BaseTool
from tools.tool_result import ToolResult, ResultStatus
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel


class LocalRunCheckpointTool(BaseTool):
    def __init__(self):
        self.name = "LocalRunCheckpointTool"
        self.description = "Manage local run checkpoints"
        self.checkpoints_dir = "data/run_checkpoints"
        Path(self.checkpoints_dir).mkdir(parents=True, exist_ok=True)
        super().__init__()

    def register_capabilities(self):
        """Register tool capabilities."""
        create_cap = ToolCapability(
            name="create",
            description="Create or update a run checkpoint",
            parameters=[
                Parameter(name="checkpoint_id", type=ParameterType.STRING, description="Unique checkpoint id"),
                Parameter(name="notes", type=ParameterType.STRING, description="Checkpoint notes"),
                Parameter(name="tags", type=ParameterType.LIST, description="Optional tags", required=False, default=None),
                Parameter(name="metadata", type=ParameterType.DICT, description="Optional metadata", required=False, default=None),
                Parameter(name="status", type=ParameterType.STRING, description="Checkpoint status", required=False, default="active"),
            ],
            returns="Checkpoint create/update result",
            safety_level=SafetyLevel.LOW,
            examples=[{"checkpoint_id": "demo-001", "notes": "baseline", "tags": ["smoke"]}],
            dependencies=[],
        )
        read_cap = ToolCapability(
            name="read",
            description="Read checkpoint by id",
            parameters=[
                Parameter(name="checkpoint_id", type=ParameterType.STRING, description="Unique checkpoint id"),
            ],
            returns="Checkpoint payload",
            safety_level=SafetyLevel.LOW,
            examples=[{"checkpoint_id": "demo-001"}],
            dependencies=[],
        )
        list_cap = ToolCapability(
            name="list",
            description="List latest checkpoints",
            parameters=[
                Parameter(name="limit", type=ParameterType.INTEGER, description="Max checkpoints to return", required=False, default=10),
            ],
            returns="Checkpoint list payload",
            safety_level=SafetyLevel.LOW,
            examples=[{"limit": 3}],
            dependencies=[],
        )

        self.add_capability(create_cap, self._handle_create)
        self.add_capability(read_cap, self._handle_read)
        self.add_capability(list_cap, self._handle_list)
        return list(self.get_capabilities().values())

    def execute(self, operation: str, **kwargs) -> ToolResult:
        """Execute tool operation."""
        if operation == "create":
            return self._handle_create(**kwargs)
        if operation == "read":
            return self._handle_read(**kwargs)
        if operation == "list":
            return self._handle_list(**kwargs)
        return ToolResult(
            tool_name=self.name,
            capability_name=operation,
            status=ResultStatus.FAILURE,
            error_message=f"Unsupported operation: {operation}",
        )

    def _checkpoint_path(self, checkpoint_id: str) -> Path:
        safe_id = checkpoint_id.strip()
        return Path(self.checkpoints_dir) / f"{safe_id}.json"

    def _handle_create(
        self,
        checkpoint_id: str,
        notes: str,
        tags=None,
        metadata=None,
        status: str = "active",
    ) -> ToolResult:
        if not isinstance(checkpoint_id, str) or not checkpoint_id.strip():
            return ToolResult(
                tool_name=self.name,
                capability_name="create",
                status=ResultStatus.FAILURE,
                error_message="checkpoint_id is required",
            )
        if not isinstance(notes, str) or not notes.strip():
            return ToolResult(
                tool_name=self.name,
                capability_name="create",
                status=ResultStatus.FAILURE,
                error_message="notes is required",
            )
        if tags is None:
            tags = []
        if metadata is None:
            metadata = {}
        if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
            return ToolResult(
                tool_name=self.name,
                capability_name="create",
                status=ResultStatus.FAILURE,
                error_message="tags must be a list of strings",
            )
        if not isinstance(metadata, dict):
            return ToolResult(
                tool_name=self.name,
                capability_name="create",
                status=ResultStatus.FAILURE,
                error_message="metadata must be an object",
            )
        if not isinstance(status, str) or not status.strip():
            return ToolResult(
                tool_name=self.name,
                capability_name="create",
                status=ResultStatus.FAILURE,
                error_message="status must be a non-empty string",
            )

        checkpoint = {
            "checkpoint_id": checkpoint_id.strip(),
            "notes": notes.strip(),
            "tags": tags,
            "metadata": metadata,
            "status": status.strip(),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
        path = self._checkpoint_path(checkpoint_id)
        path.write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")
        return ToolResult(
            tool_name=self.name,
            capability_name="create",
            status=ResultStatus.SUCCESS,
            data=checkpoint,
        )

    def _handle_read(self, checkpoint_id: str) -> ToolResult:
        if not isinstance(checkpoint_id, str) or not checkpoint_id.strip():
            return ToolResult(
                tool_name=self.name,
                capability_name="read",
                status=ResultStatus.FAILURE,
                error_message="checkpoint_id is required",
            )
        path = self._checkpoint_path(checkpoint_id)
        if not path.exists():
            return ToolResult(
                tool_name=self.name,
                capability_name="read",
                status=ResultStatus.FAILURE,
                error_message=f"Checkpoint not found: {checkpoint_id}",
            )
        data = json.loads(path.read_text(encoding="utf-8"))
        return ToolResult(
            tool_name=self.name,
            capability_name="read",
            status=ResultStatus.SUCCESS,
            data=data,
        )

    def _handle_list(self, limit: int = 10) -> ToolResult:
        if not isinstance(limit, int) or limit < 1 or limit > 50:
            return ToolResult(
                tool_name=self.name,
                capability_name="list",
                status=ResultStatus.FAILURE,
                error_message="limit must be an integer between 1 and 50",
            )

        items = []
        for path in Path(self.checkpoints_dir).glob("*.json"):
            try:
                items.append(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
        items.sort(key=lambda d: str(d.get("timestamp_utc", "")), reverse=True)
        return ToolResult(
            tool_name=self.name,
            capability_name="list",
            status=ResultStatus.SUCCESS,
            data=items[:limit],
        )
