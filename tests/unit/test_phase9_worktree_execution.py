import json
from pathlib import Path
from types import SimpleNamespace

from application.services.worktree_execution_service import WorktreeExecutionService
from application.services.worktree_task_service import WorktreeTaskService


def _isolated_plan(tmp_path):
    plan = SimpleNamespace()
    setattr(
        plan,
        "workflow_metadata",
        {
            "planning_mode": "deep",
            "execution_mode": "isolated_worktree",
            "worktree": {
                "label": "feature-a",
                "git_root": str(tmp_path),
                "worktree_path": str(tmp_path / ".worktrees" / "feature-a"),
            },
        },
    )
    return plan


def test_worktree_execution_service_reroots_repo_file_parameters(tmp_path):
    service = WorktreeExecutionService()
    plan = _isolated_plan(tmp_path)
    step = SimpleNamespace(tool_name="FilesystemTool")

    params, metadata = service.apply_to_step(
        step=step,
        parameters={"path": "README.md", "destination": str((tmp_path / "docs" / "guide.md").resolve())},
        plan=plan,
    )

    worktree_root = tmp_path / ".worktrees" / "feature-a"
    assert params["path"] == str((worktree_root / "README.md").resolve())
    assert params["destination"] == str((worktree_root / "docs" / "guide.md").resolve())
    assert metadata["execution_mode"] == "isolated_worktree"
    assert "path" in metadata["changed_keys"]
    assert "destination" in metadata["changed_keys"]


def test_worktree_execution_service_sets_shell_working_directory(tmp_path):
    service = WorktreeExecutionService()
    plan = _isolated_plan(tmp_path)
    step = SimpleNamespace(tool_name="ShellTool")

    params, metadata = service.apply_to_step(
        step=step,
        parameters={"command": "git", "arguments": ["status", "--short"]},
        plan=plan,
    )

    assert params["working_dir"] == str((tmp_path / ".worktrees" / "feature-a").resolve())
    assert metadata["tool_name"] == "ShellTool"
    assert "working_dir" in metadata["changed_keys"]


def test_worktree_execution_service_blocks_relative_path_escape(tmp_path):
    service = WorktreeExecutionService()
    plan = _isolated_plan(tmp_path)
    step = SimpleNamespace(tool_name="FilesystemTool")

    try:
        service.apply_to_step(
            step=step,
            parameters={"path": "..\\outside.txt"},
            plan=plan,
        )
    except ValueError as exc:
        assert "path escape" in str(exc)
    else:
        raise AssertionError("Expected isolated path escape to be blocked")


def test_worktree_execution_service_records_activity_metadata(tmp_path):
    service = WorktreeExecutionService()
    plan = _isolated_plan(tmp_path)
    step = SimpleNamespace(tool_name="FilesystemTool")
    worktree_root = tmp_path / ".worktrees" / "feature-a"
    worktree_root.mkdir(parents=True, exist_ok=True)
    WorktreeTaskService._write_metadata(
        worktree_root,
        {
            "version": 1,
            "label": "feature-a",
            "git_root": str(tmp_path),
            "worktree_path": str(worktree_root),
            "created_at": "2026-04-01T00:00:00+00:00",
            "last_activity_at": "2026-04-01T00:00:00+00:00",
        },
    )

    service.apply_to_step(
        step=step,
        parameters={"path": "README.md"},
        plan=plan,
    )

    metadata_path = worktree_root / WorktreeTaskService.METADATA_FILENAME
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert payload["last_routed_at"]
    assert payload["last_activity_details"]["tool_name"] == "FilesystemTool"
